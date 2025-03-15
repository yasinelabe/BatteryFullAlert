# Battery Full Alert Application Documentation

## Overview
The **Battery Full Alert** application is a desktop tool designed to monitor your laptop's battery status and notify you when the battery reaches a user-defined alert level. It provides real-time battery monitoring, customizable settings, and sound alerts to ensure you are promptly informed about your battery's charging status.

---

## Features

### 1. **Real-Time Battery Monitoring**
- Continuously monitors the battery percentage and charging status.
- Displays a line chart showing the battery level trend over time.
- Updates every 5 seconds to provide accurate and up-to-date information.

### 2. **Customizable Alert Settings**
- Set a custom battery percentage threshold for triggering alerts (e.g., 90%).
- Choose a sound file to play when the alert is triggered.
- Adjust the volume of the alert sound using a slider.

### 3. **Sound Management**
- Upload and manage sound files for alerts.
- Test and preview selected sounds before saving them.
- Stop the alert sound manually or automatically when the charger is unplugged.

### 4. **Notifications**
- Native Windows toast notifications for battery alerts and settings updates.
- Fallback tray notifications if toast notifications fail.
- Persistent tray icon for easy access to the application.

### 5. **System Tray Integration**
- Minimizes to the system tray instead of closing, ensuring continuous monitoring in the background.
- Provides quick access to restore or quit the application from the tray menu.


---

## User Interface

### 1. **Monitoring Tab**
- Displays a real-time line chart showing the battery level trend.
- Shows the current battery percentage and charging status.

### 2. **Settings Tab**
- **Choose Sound**: Upload a new sound file or select an existing one from the list.
- **Test Sound**: Preview the selected sound.
- **Stop Sound**: Manually stop the currently playing alert sound.
- **Volume Control**: Adjust the alert sound volume using a slider.
- **Set Battery Alert Percentage**: Define the battery percentage at which the alert should trigger.

### 3. **System Tray Icon**
- Accessible from the system tray for quick actions:
  - Restore the application window.
  - Quit the application.

---


## Installation

### Requirements
- Python 3.8 or higher.
- Required Python libraries: `psutil`, `plyer`, `win10toast`, `pyqtgraph`, `PyQt6`, `pygame`, `sqlite3`.

### Steps to Install
1. Clone the repository or download the source code.
2. Install dependencies using the following command:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the application:
   ```bash
   python main.py
   ```