# Junior Desktop 🖥️ – AI-Assisted LinkedIn Engagement

Junior Desktop helps you stay active on LinkedIn without living there.  It searches for high-value posts, generates context-aware comments with our AI backend, and publishes them using advanced anti-bot stealth.

---

## 1 · Download & Install

| OS | Package | Install Steps |
|----|---------|--------------|
| **Windows 10/11** | `Junior Setup x.y.z.exe` | 1. Download from the **Releases** page.<br>2. Double-click the installer.<br>3. Follow the wizard. |
| **macOS 12 +** | `Junior-x.y.z.dmg` | 1. Open the DMG.<br>2. Drag **Junior** into **Applications**. |
| **Linux (Ubuntu / Debian)** | `.AppImage` or `.deb` | • AppImage → `chmod +x` then double-click.<br>• `.deb` → `sudo dpkg -i junior-x.y.z.deb`. |

After installation you'll find a **Junior AI** shortcut in your Start menu / Launchpad.

---

## 2 · First-Time Setup

1. **Purchase & Download**  
   • Go to [heyjunior.ai](https://heyjunior.ai) and pick your plan.  
   • After checkout (Stripe) the download starts automatically.  
   • Your e-mail is pre-registered in our backend via a Stripe webhook.

2. **Install Junior** – see table above.

3. **Launch & Create Password**  
   • On first run, Junior asks you to **create a password**.  
   • Enter the **same e-mail** you used at checkout.  
   • Click **Create Password** – your backend account is now activated.

4. **Log In**  
   Enter the e-mail + password you just set and press **Log in**.  
   Status turns ✅ *Authenticated*.

5. **Configure Settings**  
   Choose keywords, daily caps, work hours, etc. and click **Save**.

6. **Start Automation**  
   Click **Start Session**. Junior opens an undetected Chrome window, warms up, then begins commenting.  
   You can minimise the window; Junior continues in the tray / menu-bar.

---

## 3 · Tray / Menu-Bar Controls

| Action | What it does |
|--------|--------------|
| **Pause** | Immediately stops actions, keeps Chrome open |
| **Resume** | Continues from where it paused |
| **Force New Session** | Closes current Chrome, opens a fresh one |
| **View Logs** | Opens `linkedin_commenter.log` |
| **Quit** | Shuts down Junior & Chrome |

---

## 4 · How Junior Works

1. Searches LinkedIn for posts matching your niche and freshness rules.  
2. Scores each post and requests a comment from `/api/comments/generate`.  
3. Types the comment with human-like speed & hesitation.  
4. Posts it, tracks history, and moves on.  
5. Uses undetected-chromedriver, JA3 / HTTP-2 randomisation, pre-page JS patching, timing jitter and realistic mouse/scroll patterns.

---

## 5 · FAQ

**Can I browse LinkedIn in my normal browser while Junior runs?**  
Yes. Junior launches its own isolated Chrome profile; your personal session is separate.

**Can I stay logged-in on the LinkedIn mobile app?**  
Yes. LinkedIn supports multiple concurrent logins. Junior's cookies are sandboxed.

**What if I manually comment on the same post?**  
Junior keeps local & cloud history and will skip posts already commented on.

**Will LinkedIn detect me as a bot?**  
Nothing is 100 %, but Junior applies current best practice stealth techniques.

**Do I need proxies?**  
No. Junior works fine from your residential IP. Proxies are optional in **Settings → Network**.

**How many comments per day can I set?**  
Go to **Settings → Limits** and adjust daily, hourly, and session caps.

**Where are log files?**  
Windows: `%APPDATA%\junior-desktop\linkedin_commenter.log`  
macOS: `~/Library/Logs/Junior/linkedin_commenter.log`  
Linux: `~/.config/junior-desktop/linkedin_commenter.log`

**How do I change or cancel my plan?**  
Use the Stripe customer-portal link in your receipt or **Settings → Billing**.

---

## 6 · For Developers / Power Users

### Clone & Run

```bash
git clone https://github.com/your-org/junior-desktop.git
cd junior-desktop
npm install                 # Electron deps
pip install -r src/resources/scripts/requirements.txt
npm run dev                 # Launch dev build
```

### API Integration Test

```bash
# Using env token
env ACCESS_TOKEN=xyz python integration_test_generate_comment.py

# Or credentials
python integration_test_generate_comment.py \
       --email you@example.com --password Secret123
```

### Build Installers

```bash
npm run clean      # remove old artefacts
npm run build:win  # Windows
npm run build:mac  # macOS
npm run build:linux
```

Installers land in `dist-build/`; standalone Python executables in `resources/python-executables/`.

---

## 7 · License

This repository is **proprietary** – redistribution or commercial use without permission is prohibited.  
For licensing enquiries e-mail **support@junior.ai**.

---

Happy networking!  
*The Junior Team*
