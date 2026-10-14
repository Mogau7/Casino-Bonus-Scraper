# Casino-Bonus-Scraper

I built this simple app to collect bonus details from online casinos and show them nicely on a mobile-friendly webpage.

How to Setup and Run

1. Download or clone this folder to your computer.
2. Open your terminal inside this folder and run the scraper script to create the data file:bash
python scrape.py
Use code with caution.
3. Open the index.html file in any normal browser to view the table.

Scaling Plan: How I'd Track 200+ Sites Daily

• Where it runs: I would put this app inside a Docker container and host it on a small, cheap Linux server, like a DigitalOcean Droplet for about 6 USD a month. This keeps the monthly bills completely steady and predictable.
• The Database and Backups: I would stop using static JSON files and move the data to a proper PostgreSQL database. I would write a simple script to run automatically every night, make a copy of the database, and upload that backup file to a safe cloud storage bucket like AWS S3.
• Domain and Security: I would route the website domain name through Cloudflare. This gives the site free HTTPS security right out of the box and stops target websites from blocking our scraper script.
• Scheduling and Error Checks: I would use a standard system Cron job to start the Python scraper script every morning at an off-peak time, like 2:00 AM. To track errors, I would connect the app to Sentry. If a casino changes its website layout and our script breaks, Sentry will instantly send an alert to my private Discord or Slack channel so I can jump in and fix it right away.
• Monthly Cost: It would cost roughly 15 USD to 22 USD a month total to run this whole system at scale.

AI Assistant Notes

• Tool used: I built this project in active collaboration with Claude.
• Where it went wrong: While building the web table, the AI initially hid the data rows using an incorrect layout style, making the table look completely blank on the screen. I caught the issue using my browser's Inspect Developer Tools, fixed the CSS padding by hand, and got the rows displaying correctly on mobile screens.

Total Time Taken

It took me exactly 2 hours and 15 minutes of focused development to complete this task.
