# E-mail Reporter

IF you don't use artifacts upload to read Mega-Linter reports, you can receive them by e-mail

## Usage

Define related variables below allowing to send e-mails

## Configuration

| Variable | Description | Default value |
| ----------------- | -------------- | :--------------: |
| EMAIL_REPORTER | Activates/deactivates reporter | true |
| EMAIL_REPORTER_EMAIL | Comma-separated list of recipient emails, that will receive reports |  |
| EMAIL_REPORTER_SENDER | Sender of emails | megalinter@gmail.com |
| EMAIL_REPORTER_SMTP_HOST | SMTP server host | smtp.gmail.com |
| EMAIL_REPORTER_SMTP_PORT | SMTP server port | 465 |
| EMAIL_REPORTER_SMTP_USERNAME | SMTP server username | megalinter@gmail.com |
| EMAIL_REPORTER_SMTP_PASSWORD | SMTP server password. Never hardcode it in a config variable, use secrets and context variables |  |