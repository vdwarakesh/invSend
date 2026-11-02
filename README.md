# invSend - User Guide

invSend automatically finds the right emails, gets the phone number from them, and sends that person a WhatsApp message with a screenshot of the email and the correct document attached - so you don't have to do it by hand, one by one.

## How to start it

1. Open the invSend folder.
2. Double-click the file called **main**.
3. A command prompt will open and stay open while it works - that's normal, just leave it alone.
4. When it's finished, it will say **"Automation complete."**

**If anything ever goes wrong or gets stuck:** close the command prompt and double-click **main** again. That fixes almost everything.

## The very first time you use it

A couple of one-time steps happen only the first time:

1. **A QR code will appear in the command prompt.** Open WhatsApp on your phone, go to **Settings > Linked Devices > Link a Device**, and scan it. Do this quickly - if it disappears before you scan it, just wait a moment and a new one will show up.
2. **A Chrome window will open by itself.** The first time, you'll need to log into your own Gmail account in that window, like you normally would. After that, it will remember you and won't ask again.

After this first-time setup, every future run just works - double-click and go.

## What it actually does each time you run it

1. Looks through your Gmail for the emails it's set up to look for.
2. Opens each one and looks for a phone number inside it.
3. If it finds one, it sends that person a WhatsApp message, a screenshot of the email, and the right document - automatically.
4. It does this for each matching email, up to a safe limit per run, so it doesn't send too many messages at once.

## When someone doesn't get a message

Sometimes invSend isn't confident about which message or document belongs to an email, and in that case **it won't guess** - it skips that person rather than risk sending the wrong thing.

Every time this happens, it's written down in a file called **not-sent.txt**, in the same folder. It lists the phone number, who the email was from, the subject, and why it was skipped. Check this file after each run so you know who still needs a message sent to them manually.

## Your information stays on your computer

Everything invSend needs - your WhatsApp connection and your Gmail login - is saved only inside this one folder on your computer. Nothing is sent anywhere else. If this folder is ever deleted, everything connected to it (your WhatsApp link, your Gmail login) is removed completely, with nothing left behind.

## If something isn't working

Just **close the program and open it again** This solves the vast majority of issues, since it picks up right where it needs to and reconnects automatically.

If problems keep happening even after restarting a few times, reach out for help rather than trying to fix it yourself.