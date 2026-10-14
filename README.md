# Casino Bonus Scraper

This is a simple full-stack app built to grab bonus information from online casinos and show it nicely on a mobile-friendly webpage. 

##  How to Setup and Run
1. Download or clone this folder onto your computer.
2. To build the data file, open your terminal inside this folder and run:
   ```bash
   python scrape.py
   ```
3. Open the `index.html` file in any normal web browser to see the live mobile-first table interface.

## Scaling Plan: How I'd Take This to 200+ Sites Daily

*   **Where it runs:** I would put this inside a Docker container and host it on a small, cheap Linux server (like a DigitalOcean Droplet for \$6/month). It keeps monthly bills predictable.
*   **The Database & Backups:** I would move away from static JSON files and use a PostgreSQL database. I would set up a simple script to run every night, make a backup of the data, and automatically upload that backup to a safe cloud bucket like AWS S3.
*   **Domain & Security:** I would route the website domain name through Cloudflare. This gives the site free, automatic HTTPS security (the lock icon in the browser) and stops target websites from blocking our scraper script.
*   **Scheduling & Error Checks:** I would use a standard system Cron job to trigger the Python scraper every morning at an off-peak time (like 2:00 AM). To track failures, I would connect the script to Sentry. If a casino changes its website layout and our script breaks, Sentry will instantly ping an alert to my private Discord or Slack channel so I can fix it.
*   **Monthly Cost:** It would cost roughly \$15 to \$22 per month total to run this at scale.

##  AI Co-Pilot Notes
*   **Tool used:** I built this project in active collaboration with Claude.
*   **Where it went wrong:** While building the frontend table, the AI initially hid the data rows using a messy layout style, making the table look completely blank on the screen. I caught the issue using my browser's Inspect Developer Tools, fixed the CSS padding by hand, and got the rows displaying beautifully on mobile viewports.

##  Total Time Taken
It took me exactly 2 hours and 15 minutes to complete this task.
