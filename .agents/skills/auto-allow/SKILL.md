---
name: auto-allow
description: >-
  Automatically configure and grant full permissions in Google Antigravity, switching
  Tool Execution Policy to always-proceed (Turbo Mode), auto-authorizing terminal commands
  and file operations, and eliminating manual "Yes, allow this time" or review confirmation prompts.
---

# Auto-Allow: Automatic Permission & Turbo Execution System

This skill configures Antigravity to operate in full autonomous mode ("Turbo Mode") without pausing to ask the user "Yes, allow this time", "Allow", or "Request review" for tool executions, commands, and file edits.

## 1. Overview & Root Cause

By default, Antigravity protects the host system by setting **Tool Execution Policy** to `request-review`. Every time a new command (`command(...)`), file read (`read_file(...)`), or file write (`write_file(...)`) is requested, Antigravity prompts the user for manual confirmation.

This skill eliminates those interruptions through three complementary layers:

1. **Config Injection (`config.json`)**: Injects universal wildcard permission grants (`command(*)`, `read_file(*)`, `write_file(*)`, `*`) into `globalPermissionGrants.allow` and sets `toolExecutionPolicy: "always-proceed"`.
2. **CLI Settings (`settings.json`)**: Configures `toolPermission: "always-proceed"` and registers trusted workspaces.
3. **Background Auto-Clicker Daemon (`auto_clicker.ps1`)**: A lightweight Windows background watcher that monitors for any remaining UI modals containing "Yes, allow this time" or "Allow" and automatically clicks them in real time.

---

## 2. Quick Usage

Run the bundled batch script:

```bat
auto_allow_yes.bat
```

Or pass flags directly:

- `auto_allow_yes.bat --apply` : Immediately applies Turbo Mode and wildcard permissions to `config.json`.
- `auto_allow_yes.bat --watch` : Runs the background auto-clicker watcher.
- `auto_allow_yes.bat --all`   : Applies configuration and starts the watcher.

---

## 3. Manual Configuration (Settings UI)

If configuring via Antigravity Desktop or IDE UI:

1. Click the **Settings** icon (gear ⚙️ in the bottom-left sidebar).
2. Navigate to **Agent Settings & Permissions**.
3. Under **Tool Execution Policy**, select:
   - **`always-proceed`** (Turbo Mode / Auto-execute without confirmation).
4. Set **Non-Workspace File Access** to **Allow**.
5. Set **Internet Access Policy** to **Allow**.

---

## 4. Reverting to Default

To revert back to standard confirmation mode:

- Run `auto_allow_yes.bat` and select Option `[4] Restore Original Backup`, OR
- In Antigravity Settings UI, set **Tool Execution Policy** back to **`request-review`**.
