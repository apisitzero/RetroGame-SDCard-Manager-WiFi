# ==============================================================================
# Antigravity Auto-Allow Background Watcher (PowerShell)
# Automatically clicks "Yes, allow this time" or "Allow" confirmation buttons.
# ==============================================================================

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " [Auto-Allow Watcher] Background Daemon Started" -ForegroundColor Yellow
Write-Host " Monitoring for Antigravity permission prompts..." -ForegroundColor White
Write-Host " Press Ctrl+C in this window to stop monitoring." -ForegroundColor Gray
Write-Host "==========================================================" -ForegroundColor Cyan

Add-Type -AssemblyName UIAutomationClient -ErrorAction SilentlyContinue
Add-Type -AssemblyName UIAutomationTypes -ErrorAction SilentlyContinue

$buttonCondition = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::Button
)

$targetKeywords = @("allow this time", "yes, allow", "allow", "อนุญาต", "always allow")

while ($true) {
    try {
        $root = [System.Windows.Automation.AutomationElement]::RootElement
        $buttons = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $buttonCondition)

        foreach ($btn in $buttons) {
            try {
                $name = $btn.Current.Name
                if (-not [string]::IsNullOrWhiteSpace($name)) {
                    $lowerName = $name.ToLower().Trim()
                    
                    # Check if button matches permission approval keywords
                    $matched = $false
                    foreach ($kw in $targetKeywords) {
                        if ($lowerName -like "*$kw*") {
                            $matched = $true
                            break
                        }
                    }

                    if ($matched) {
                        # Verify parent window is Antigravity or related
                        $window = [System.Windows.Automation.TreeWalker]::ControlViewWalker.GetParent($btn)
                        $invokePattern = $btn.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
                        if ($invokePattern) {
                            $timestamp = Get-Date -Format "HH:mm:ss"
                            Write-Host "[$timestamp] [Auto-Allow] Found '$name' -> Auto-approved!" -ForegroundColor Green
                            $invokePattern.Invoke()
                            Start-Sleep -Milliseconds 300
                        }
                    }
                }
            } catch {}
        }
    } catch {}

    Start-Sleep -Milliseconds 400
}
