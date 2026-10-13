# Website Monitor

A tool that checks if a website is up or down.

I made this because I needed to download data from a website, but the server for the website was down. I didn't want to keep refreshing the page to see if it was back up, so this checks it for me. You put in the website, set how often it should check (1 min, 5 min, etc.), and it tells you if the website is still down or if it's back up.

![Website Monitor](docs/screenshot.png)

## What it does

- Checks the website on a time interval, from every 30 seconds to every 60 minutes
- You can also check it right away with Check now
- Shows ONLINE or DOWN
- When the website comes back up, it plays a sound and shows a pop-up
- Graph that shows the response time for each check. Red is when the website was down
- Log of every check with the time and the result
- Dark mode
- Saves the last website and settings you used

## What you need

- Windows
- ArcGIS Pro. The tool runs on the Python that comes with ArcGIS Pro, so you don't need to install anything else

If you don't have ArcGIS Pro, any Python 3 with tkinter will work. Run `pythonw website_monitor.py`.

## How to use it

1. Download the files and keep them in the same folder
2. Double-click `Run Website Monitor.bat`
3. Put in the website, pick how often to check, and click Start

You can minimize it and it will keep checking.

### Desktop shortcut with the icon

If you want an icon on your desktop to open it:

1. Right-click the desktop, then New > Shortcut
2. For the location, put:
   ```
   "C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\pythonw.exe" "C:\path\to\folder\website_monitor.py"
   ```
   Change `C:\path\to\folder` to where you saved the files
3. Name it `Website Monitor`
4. Right-click the shortcut, then Properties > Change Icon, and pick `website_monitor.ico`

## How it decides if the website is up or down

It tries to load the website and waits up to 30 seconds.

- **Up:** the website responds (anything under a 500 error, like 200 OK or 404)
- **Down:** a 500 error (like 502 or 503, which is what you usually get when a server is down), no response after 30 seconds, or it can't connect at all

## Files

- `website_monitor.py`: the tool
- `Run Website Monitor.bat`: double-click this to open the tool
- `website_monitor.ico`: the icon
- `make_icon.py`: makes the icon. Edit it and run it if you want to change the icon
