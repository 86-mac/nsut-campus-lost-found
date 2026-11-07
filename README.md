# NSUT Campus Lost & Found

A Flask + MySQL/MariaDB campus lost-and-found portal. Local development uses XAMPP; public deployment requires a hosted MySQL-compatible database, persistent file storage for uploads, and SMTP credentials for email delivery.

## Features

- Student registration/login with securely hashed passwords
- Login alert email (when SMTP is configured)
- Forgot-password email with a one-time link that expires after 30 minutes
- Item photo upload and display (JPG, PNG, WEBP, GIF; max 5 MB)
- User profile photo upload/change
- Lost/found item reports, browse and search
- Found-item claims, admin approval/rejection, in-app notifications and email alerts
- Admin dashboard to view all users, reports and claims; change item status and user roles

## Run locally on macOS with XAMPP

1. Start **MySQL Database** in XAMPP Manager.
2. From this folder, activate your virtual environment and install dependencies:
   ```bash
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. Import/update the schema (safe to run on the existing project database):
   ```bash
   /Applications/XAMPP/xamppfiles/bin/mysql -u root < schema.sql
   ```
4. Start the app:
   ```bash
   python app.py
   ```
5. Open http://127.0.0.1:5000.

Uploaded photos are saved under `static/uploads`. Back up this folder with the database.

## Configure email (SMTP)

Email delivery is optional in local development and is activated only when these environment variables are configured:

```bash
export SMTP_HOST="smtp.gmail.com"
export SMTP_PORT="587"
export SMTP_USERNAME="your-sending-gmail@gmail.com"
export SMTP_PASSWORD="your-16-character-google-app-password"
export SMTP_FROM="your-sending-gmail@gmail.com"
```

For Gmail, enable 2-Step Verification and create an **App Password**. Do not use your normal Google account password. Keep SMTP credentials out of GitHub. On a hosting provider, add these values in the service's private Variables/Environment settings instead of committing them to files. Without SMTP settings, the site still works and stores in-app notifications, but emails will not be delivered.

Emails are sent for account registration, successful login alerts, password-reset requests, new claims, claim decisions, and admin item-status changes. The app never emails a user's password.

## Make your first administrator

1. Register your own account through the website.
2. Run this command, replacing the email with the exact registered email:
   ```bash
   /Applications/XAMPP/xamppfiles/bin/mysql -u root -D campus_lost_found -e "UPDATE users SET role='admin' WHERE email='YOUR_EMAIL_HERE';"
   ```
3. Log out and log in again. The **Admin** link appears in the navigation.

An admin can open `/admin`, review all users/items, change item status to Open/Claimed/Returned/Resolved, promote trusted users to admin, and open **Claims** to approve or reject claims. The app prevents an admin from changing their own role through the dashboard.

## Public deployment

The local XAMPP database and `127.0.0.1` address are not public. To make the app available from other devices, deploy the Flask app and create a hosted MySQL-compatible database. Configure `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `FLASK_SECRET`, and the SMTP variables in the hosting provider's environment settings. Import `schema.sql` into the hosted database. Use persistent object/file storage for uploaded images in production; the local `static/uploads` directory may be ephemeral on some hosts.

Never commit database passwords, SMTP app passwords, or `.env` files to GitHub. This is a DBMS project starter and should receive CSRF protection, rate limiting, secure cookie settings, backups, and a security review before real public use.
