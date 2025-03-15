from sys import (
    platform, exit, argv
)
from os import (
    path, makedirs, remove, getenv, listdir
)
from psutil import sensors_battery
from pythoncom import CoInitialize
from win10toast import ToastNotifier
from pyqtgraph import (
    PlotWidget,
    mkPen,
    PlotCurveItem,
    FillBetweenItem,
)
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QTabWidget, QPushButton, QListWidget,
    QHBoxLayout, QFileDialog, QSlider, QSystemTrayIcon, QMenu, QSpinBox, QMessageBox
)
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtCore import QTimer, Qt, pyqtSignal, QObject
from sqlite3 import (connect, OperationalError)

DARK_THEME = """
    QWidget { background-color: #1e1e1e; color: white; }
    QPushButton { background-color: #333; border: 1px solid #555; }
    QPushButton:hover { background-color: #444; }
    QProgressBar { background-color: #444; border: 1px solid #666; color: white; }
    QProgressBar::chunk { background-color: #4caf50; }
"""


class Database:
    """Handles SQLite3 database operations."""

    def __init__(self, db_name="battery_alert.db", app_name="BatteryAlertApp"):
        self.app_data_dir = get_app_data_directory(app_name)
        self.db_path = path.join(self.app_data_dir, db_name)
        makedirs(self.app_data_dir, exist_ok=True)
        try:
            self.conn = connect(self.db_path)
            self.cursor = self.conn.cursor()
        except OperationalError as e:
            print(f"Failed to connect to database: {e}")
            raise
        self.cursor = self.conn.cursor()
        self.create_tables()

    def create_tables(self):
        """Creates necessary tables if they don't exist."""
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY,
                sound_file TEXT,
                volume REAL,
                alert_percentage INTEGER
            )
        """)
        self.conn.commit()

    def load_settings(self):
        """Loads settings from the database."""
        self.cursor.execute(
            "SELECT sound_file, volume, alert_percentage FROM settings WHERE id=1")
        row = self.cursor.fetchone()
        if row:
            return {"sound_file": row[0], "volume": row[1], "alert_percentage": row[2]}
        return {"sound_file": "", "volume": 1.0, "alert_percentage": 90}

    def save_settings(self, settings):
        """Saves settings to the database."""
        self.cursor.execute("""
            INSERT OR REPLACE INTO settings (id, sound_file, volume, alert_percentage)
            VALUES (1, ?, ?, ?)
        """, (settings["sound_file"], settings["volume"], settings["alert_percentage"]))
        self.conn.commit()

    def get_alert_percentage(self):
        """Retrieves the alert percentage."""
        self.cursor.execute("SELECT alert_percentage FROM settings WHERE id=1")
        row = self.cursor.fetchone()
        return row[0] if row else 90

    def set_alert_percentage(self, value):
        """Updates the alert percentage."""
        self.cursor.execute(
            "UPDATE settings SET alert_percentage=? WHERE id=1", (value,))
        self.conn.commit()

    def set_sound_file(self, file_path):
        """Updates the sound file path."""
        self.cursor.execute(
            "UPDATE settings SET sound_file=? WHERE id=1", (file_path,))
        self.conn.commit()

    def set_volume(self, volume):
        """Updates the volume level."""
        self.cursor.execute(
            "UPDATE settings SET volume=? WHERE id=1", (volume,))
        self.conn.commit()


class SoundManager:
    """Manages sound playback."""

    def __init__(self):
        import pygame
        pygame.mixer.init()
        self.pygame = pygame
        self.is_playing = False

    def play_sound(self, file_path, loop=False):
        """Plays a sound file."""
        if not self.is_playing:
            self.pygame.mixer.music.load(file_path)
            self.pygame.mixer.music.play(-1 if loop else 0)
            self.is_playing = True

    def stop_sound(self):
        """Stops the currently playing sound."""
        if self.is_playing:
            self.pygame.mixer.music.stop()
            self.is_playing = False

    def set_volume(self, volume):
        """Sets the volume level."""
        self.pygame.mixer.music.set_volume(volume)


class BatterySignals(QObject):
    update_progress = pyqtSignal(int)
    update_status = pyqtSignal(str)
    play_alert = pyqtSignal()
    update_style = pyqtSignal()


class BatteryAlertApp(QWidget):
    def __init__(self):
        super().__init__()
        self.db = Database()
        self.settings = self.db.load_settings()
        self.monitoring = False
        self.signals = BatterySignals()
        self.sound_manager = SoundManager()
        self.sound_manager.set_volume(self.settings["volume"])
        self.battery_levels = []
        self.charging_status = "Unknown"
        self.is_playing = False
        self.testing_sound = False
        self.notification_shown = False
        self.init_ui()
        self.connect_signals()
        self.toaster = ToastNotifier()
        self.create_tray_icon()
        self.start_monitoring()

    def init_ui(self):
        """Initializes the UI."""
        self.setWindowTitle("Battery Full Alert")
        self.setGeometry(100, 100, 800, 600)
        self.setFixedSize(600, 400)
        self.center_window()
        self.setWindowIcon(QIcon("battery.ico"))
        self.setStyleSheet(DARK_THEME)

        # Tabs
        self.tabs = QTabWidget()
        self.monitoring_tab = QWidget()
        self.settings_tab = QWidget()
        self.tabs.addTab(self.monitoring_tab, "Monitoring")
        self.tabs.addTab(self.settings_tab, "Settings")

        # Monitoring Tab
        self.plot_widget = PlotWidget()
        self.plot_widget.setBackground("black")
        self.plot_widget.setTitle(
            "Battery Level Trend", color="white", size="14pt")
        self.plot_widget.setLabel("left", "Battery Level (%)", color="white")
        self.plot_widget.setLabel("bottom", "Time (Readings)", color="white")
        self.plot_widget.setYRange(0, 100)
        self.plot_widget.showGrid(x=True, y=True)
        self.battery_curve = self.plot_widget.plot(
            pen=mkPen("yellow", width=2))
        self.fill_curve = PlotCurveItem(pen=None)
        self.fill = FillBetweenItem(
            self.battery_curve, self.fill_curve, brush=(255, 255, 0, 100))
        self.plot_widget.addItem(self.fill)
        self.current_marker = self.plot_widget.plot(
            [], [], symbol="o", symbolSize=8, symbolBrush="red")

        self.battery_label = QLabel("Battery: --%")
        self.battery_label.setStyleSheet(
            "color: white; font-size: 14px; font-weight: bold;")
        self.charging_label = QLabel("Charging: Unknown")
        self.charging_label.setStyleSheet("color: lightblue; font-size: 14px;")

        monitoring_layout = QVBoxLayout()
        monitoring_layout.addWidget(self.plot_widget)
        monitoring_layout.addWidget(self.battery_label)
        monitoring_layout.addWidget(self.charging_label)
        self.monitoring_tab.setLayout(monitoring_layout)

        # Settings Tab
        self.label = QLabel(
            f"Selected Sound: {self.settings['sound_file']}", self)
        self.browse_btn = QPushButton("Choose Sound", self)
        self.browse_btn.clicked.connect(self.choose_sound)
        self.sound_list = QListWidget()
        self.sound_list.addItems(self.get_sound_files())
        self.sound_list.itemClicked.connect(self.select_existing_sound)

        self.test_btn = QPushButton("Test Sound", self)
        self.test_btn.clicked.connect(self.test_sound)
        self.stop_sound_btn = QPushButton("Stop Sound", self)
        self.stop_sound_btn.setEnabled(False)
        self.stop_sound_btn.clicked.connect(self.stop_sound)

        self.delete_sound_btn = QPushButton("Delete Sound", self)
        self.delete_sound_btn.setEnabled(False)
        self.delete_sound_btn.clicked.connect(self.delete_sound)
        self.sound_list.itemSelectionChanged.connect(
            self.update_delete_button_state)

        media_layout = QHBoxLayout()
        media_layout.addWidget(self.test_btn)
        media_layout.addWidget(self.stop_sound_btn)
        media_layout.addWidget(self.delete_sound_btn)

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setMinimum(0)
        self.volume_slider.setMaximum(100)
        self.volume_slider.setValue(int(self.settings["volume"] * 100))
        self.volume_slider.valueChanged.connect(self.update_volume)

        self.spin_box = QSpinBox()
        self.spin_box.setRange(10, 100)
        self.spin_box.setValue(self.db.get_alert_percentage())
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self.save_alert_level)

        settings_layout = QVBoxLayout()
        settings_layout.addWidget(self.label)
        settings_layout.addWidget(self.browse_btn)
        settings_layout.addWidget(self.sound_list)
        settings_layout.addLayout(media_layout)
        settings_layout.addWidget(QLabel("Volume Control"))
        settings_layout.addWidget(self.volume_slider)
        settings_layout.addWidget(QLabel("Set Battery Alert Percentage:"))
        settings_layout.addWidget(self.spin_box)
        settings_layout.addWidget(self.save_button)
        self.settings_tab.setLayout(settings_layout)

        main_layout = QVBoxLayout()
        main_layout.addWidget(self.tabs)
        self.setLayout(main_layout)

    def start_monitoring(self):
        """Starts battery monitoring."""
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_chart)
        self.timer.start(5000)

    def update_chart(self):
        """Updates the chart and checks for alerts."""
        battery = sensors_battery()
        if battery:
            battery_percent = battery.percent
            self.battery_levels.append(battery_percent)
            self.charging_status = "Plugged In" if battery.power_plugged else "On Battery"

            if len(self.battery_levels) > 50:
                self.battery_levels.pop(0)

            x_values = list(range(len(self.battery_levels)))
            self.battery_curve.setData(x_values, self.battery_levels)
            self.fill_curve.setData(x_values, [0] * len(x_values))
            self.current_marker.setData([x_values[-1]], [battery_percent])

            self.battery_label.setText(f"Battery: {battery_percent}%")
            self.charging_label.setText(f"Charging: {self.charging_status}")

            if battery.power_plugged and battery_percent >= self.db.get_alert_percentage():
                if not self.notification_shown:
                    self.show_windows_notification(
                        title="Battery Full Alert",
                        message=f"Battery at {battery_percent}%. Please unplug the charger.",
                        duration=5
                    )
                    self.notification_shown = True
                if not self.is_playing:
                    self.play_alert()
            else:
                self.notification_shown = False
                if not self.testing_sound:
                    self.stop_sound()

    def connect_signals(self):
        """Connects signals to slots."""
        self.signals.play_alert.connect(self.play_alert)

    def show_windows_notification(self, title="Alert", message="", duration=5):
        """Shows a Windows toast notification."""
        try:
            CoInitialize()
            self.toaster.show_toast(
                title,
                message,
                icon_path=path.abspath("battery.ico"),
                duration=duration,
                threaded=True
            )
        except Exception as e:
            print(f"Windows notification failed: {e}")
            self.tray_icon.showMessage(
                title,
                message,
                QSystemTrayIcon.MessageIcon.Warning,
                duration * 1000
            )

    def play_alert(self):
        """Plays the alert sound."""
        if self.settings["sound_file"]:
            self.sound_manager.play_sound(
                self.settings["sound_file"], loop=True)
            self.stop_sound_btn.setEnabled(True)
            self.is_playing = True

    def stop_sound(self):
        """Stops the alert sound."""
        self.sound_manager.stop_sound()
        self.stop_sound_btn.setEnabled(False)
        self.is_playing = False
        self.testing_sound = False

    def test_sound(self):
        """Tests the selected sound."""
        if self.settings["sound_file"]:
            self.sound_manager.play_sound(self.settings["sound_file"])
            self.stop_sound_btn.setEnabled(True)
            self.testing_sound = True

    def choose_sound(self):
        """Allows the user to choose a sound file and stores it in the 'sounds' directory."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Sound File", "", "Audio Files (*.mp3 *.wav)"
        )
        if file_path:
            sounds_dir = path.join(
                get_app_data_directory("BatteryAlertApp"), "sounds")
            # Ensure 'sounds' directory exists
            makedirs(sounds_dir, exist_ok=True)
            file_name = path.basename(file_path)
            new_path = path.join(sounds_dir, file_name)

            # Copy the file to sounds directory
            if not path.exists(new_path):
                with open(file_path, "rb") as src, open(new_path, "wb") as dst:
                    dst.write(src.read())

            # Update the database with the new sound
            self.settings['sound_file'] = new_path
            self.db.set_sound_file(new_path)
            self.db.save_settings(self.settings)

            # Refresh the sound list in the UI
            self.sound_list.clear()
            self.sound_list.addItems(self.get_sound_files())

            # Update the label and set the new sound as selected
            self.label.setText(f"Selected Sound: {new_path}")

    def select_existing_sound(self, item):
        """Selects an existing sound."""
        selected_sound = item.text()
        self.settings["sound_file"] = selected_sound
        self.db.set_sound_file(selected_sound)
        self.db.save_settings(self.settings)
        self.label.setText(f"Selected Sound: {selected_sound}")

    def update_delete_button_state(self):
        """Enables or disables the Delete Sound button based on selection."""
        if self.sound_list.selectedItems():
            self.delete_sound_btn.setEnabled(True)
        else:
            self.delete_sound_btn.setEnabled(False)

    def delete_sound(self):
        """Deletes the selected sound file from the 'sounds' directory."""
        selected_items = self.sound_list.selectedItems()
        if not selected_items:
            return

        selected_sound = selected_items[0].text()
        try:
            # Delete the file from the filesystem
            remove(selected_sound)

            # Refresh the sound list in the UI
            self.sound_list.clear()
            self.sound_list.addItems(self.get_sound_files())

            # Reset the selected sound in settings if it was deleted
            if self.settings["sound_file"] == selected_sound:
                self.settings["sound_file"] = ""
                self.db.set_sound_file("")
                self.db.save_settings(self.settings)
                self.label.setText("Selected Sound: None")

            # Show a success message
            QMessageBox.information(
                self, "Success", f"Sound file deleted: {path.basename(selected_sound)}")
        except Exception as e:
            QMessageBox.critical(
                self, "Error", f"Failed to delete sound file: {e}")

    def get_sound_files(self):
        """Returns a list of sound files in the 'sounds' directory."""
        sounds_dir = path.join(
            get_app_data_directory("BatteryAlertApp"), "sounds")
        makedirs(sounds_dir, exist_ok=True)
        return [path.join(sounds_dir, f) for f in listdir(sounds_dir) if f.endswith((".mp3", ".wav"))]

    def update_volume(self, value):
        """Updates the volume."""
        volume = value / 100.0
        self.sound_manager.set_volume(volume)
        self.settings["volume"] = volume
        self.db.set_volume(volume)

    def save_alert_level(self):
        """Saves the alert level."""
        alert_level = self.spin_box.value()
        self.db.set_alert_percentage(alert_level)
        QMessageBox.information(
            self, "Success", f"Battery alert level set to {alert_level}%")

    def center_window(self):
        """Centers the window."""
        frame_geometry = self.frameGeometry()
        screen_center = self.screen().availableGeometry().center()
        frame_geometry.moveCenter(screen_center)
        self.move(frame_geometry.topLeft())

    def closeEvent(self, event):
        """Minimizes to tray on close."""
        event.ignore()
        self.hide()
        self.tray_icon.showMessage(
            "Battery Full Alert", "The app is running in the background.", QSystemTrayIcon.MessageIcon.Information, 2000)

    def create_tray_icon(self):
        """Creates the tray icon."""
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon('battery.ico'))
        self.tray_icon.setToolTip("Battery Full Alert")
        self.tray_icon.activated.connect(self.restore_from_tray)

        tray_menu = QMenu()
        show_action = QAction("Show", self)
        show_action.triggered.connect(self.show)
        tray_menu.addAction(show_action)

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.quit_app)
        tray_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

    def restore_from_tray(self, reason):
        """Restores the app from tray."""
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show()

    def quit_app(self):
        """Exits the app."""
        self.stop_monitoring()
        self.tray_icon.hide()
        QApplication.quit()

    def stop_monitoring(self):
        """Stops monitoring."""
        if hasattr(self, 'timer') and self.timer.isActive():
            self.timer.stop()


def get_app_data_directory(app_name="BatteryAlertApp"):
    """Returns the platform-specific application data directory."""
    if platform == "win32":
        # Windows: Use %APPDATA%
        app_data_dir = getenv("APPDATA")
    elif platform == "darwin":
        # macOS: ~/Library/Application Support
        app_data_dir = path.expanduser("~/Library/Application Support")
    else:
        # Linux and other Unix-like systems: ~/.local/share
        app_data_dir = path.expanduser("~/.local/share")

    # Create a subdirectory for your app
    app_dir = path.join(app_data_dir, app_name)
    makedirs(app_dir, exist_ok=True)  # Ensure the directory exists
    return app_dir


if __name__ == "__main__":
    app = QApplication(argv)
    window = BatteryAlertApp()
    window.show()
    exit(app.exec())