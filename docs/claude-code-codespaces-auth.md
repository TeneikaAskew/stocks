# Claude Code Auth in Codespaces

Quick guide for installing and authenticating Claude Code in a GitHub Codespaces browser terminal.

## Install

```bash
npm install -g @anthropic-ai/claude-code
```

Requires Node.js 18+.

## Regular Auth Flow

1. Run `claude` in the terminal.
2. When the auth prompt appears, press `c` to copy the sign-in URL to your clipboard.
3. Open the URL in a new browser tab, sign in with your Claude subscription account, and approve access.
4. Copy the auth code shown on the success page (format is usually `code#state`).
5. Click the "Paste code here if prompted >" line in the terminal and paste with `Ctrl+Shift+V`.
6. Press Enter.

## Troubleshooting

### Clipboard permission
Browser Codespaces needs clipboard access. Click the clipboard icon in the URL bar (or site settings) and allow clipboard read for `*.github.dev`.

### Command palette paste
Press `F1` → type "Terminal: Paste into Active Terminal" → Enter.

### Diagnose which command a keybinding actually fires
If a shortcut (e.g. `Ctrl+Shift+V`) seems to do nothing, find out what VS Code is actually dispatching:

1. Run `Developer: Toggle Keyboard Shortcuts Troubleshooting` from the command palette (`F1`).
2. An output panel opens and starts logging dispatched keys.
3. Press the shortcut you're testing.
4. Check the log — it will show the detected keybinding and which command (if any) was invoked. If no command fires, the key is being swallowed or unbound; if the wrong command fires, you have a keybinding conflict.

### Right-click / middle-click
- Right-click directly on the paste prompt line → Paste.
- Or select text to put it in the X11 primary selection, then middle-click in the prompt.

### Backup: long-lived token
If the regular flow keeps failing, try:
```bash
claude setup-token
```
Same paste flow, but you only need to do it once.

### Last resort: tmux injection
When the Ink TUI refuses all paste methods, inject the code via tmux:

```bash
sudo apt-get install -y tmux
tmux new -s claude
claude
```

Get a fresh auth code from the browser, then open a **second** terminal and run:
```bash
tmux set-buffer 'YOUR_CODE_HERE'
tmux paste-buffer -t claude
```

Switch back to the tmux session and press Enter.

## Notes

- OAuth codes are single-use and expire within a few minutes — always use a fresh one after restarting.
- The code format is `code#state` (includes the `#`).
- Browser Codespaces + Ink-based TUIs have known paste issues. VS Code Desktop handles terminal paste more reliably when available.
