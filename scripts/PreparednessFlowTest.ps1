Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$repoRoot = Split-Path -Parent $PSScriptRoot

function Get-CommunicationLogs {
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = "docker.exe"
    $startInfo.Arguments = "compose logs --since=2m --tail=100 communication"
    $startInfo.WorkingDirectory = $repoRoot
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true

    $process = [System.Diagnostics.Process]::Start($startInfo)
    $outputTask = $process.StandardOutput.ReadToEndAsync()
    $errorTask = $process.StandardError.ReadToEndAsync()
    if (-not $process.WaitForExit(15000)) {
        $process.Kill()
        throw "Timed out while reading communication logs."
    }

    $output = $outputTask.Result
    $errorOutput = $errorTask.Result
    if ($process.ExitCode -ne 0) {
        throw "Could not read Docker Compose logs: $errorOutput"
    }

    return $output
}

function Get-CommunicationSnapshot {
    $lines = @((Get-CommunicationLogs) -split "`r?`n")
    $decisionLines = @(
        $lines | Where-Object {
            $_ -match 'POST /preparedness_decision HTTP/1\.1" \d{3}'
        }
    )
    $taskLines = @(
        $lines | Where-Object { $_.Contains("[Camunda] Simulating") }
    )

    return @{
        Lines = $lines
        DecisionCount = $decisionLines.Count
        TaskCount = $taskLines.Count
    }
}

function Send-TestRefresh(
    [string]$locationId,
    [string]$refreshId,
    [double]$seaLevelCm,
    [double]$leadTimeHours
) {
    $policy = @{
        forecast_horizon_hours = 36
        information_lead_hours = 6
        state_lead_hours = 4
        operational_lead_hours = 2
        regions = @{
            "test-region" = @{
                category_1_min_cm = 100
                category_2_min_cm = 150
                category_3_above_cm = 200
            }
        }
        locations = @{
            $locationId = @{ region = "test-region" }
        }
    }
    $forecasts = @(
        @{
            location_id = $locationId
            sea_level_cm = $seaLevelCm
            lead_time_hours = $leadTimeHours
        }
    )
    $requestBody = @{
        refresh_id = $refreshId
        location_id = $locationId
        forecasts_json = ConvertTo-Json -InputObject $forecasts -Compress -Depth 10
        policy_json = ConvertTo-Json -InputObject $policy -Compress -Depth 10
    }
    $body = ConvertTo-Json -InputObject $requestBody -Compress -Depth 10

    Invoke-RestMethod `
        -Uri "http://localhost:7077/forecast-refreshes" `
        -Method Post `
        -ContentType "application/json" `
        -Body $body `
        -TimeoutSec 15 `
        -ErrorAction Stop | Out-Null
}

function Wait-ForDecision(
    [int]$baselineCount,
    [string]$stageName,
    [System.Windows.Forms.TextBox]$outputBox
) {
    for ($attempt = 0; $attempt -lt 15; $attempt++) {
        Start-Sleep -Seconds 2
        $snapshot = Get-CommunicationSnapshot
        if ($snapshot.DecisionCount -gt $baselineCount) {
            $line = $snapshot.Lines |
                Where-Object {
                    $_ -match 'POST /preparedness_decision HTTP/1\.1" \d{3}'
                } |
                Select-Object -Last 1
            if ($line -match 'HTTP/1\.1" (\d{3})') {
                if ($Matches[1] -ne "200") {
                    throw "$stageName decision was rejected: $line"
                }
                $outputBox.AppendText("$stageName decision accepted: $line`r`n")
                $outputBox.Refresh()
                return
            }
        }
    }

    throw "Timed out waiting for communication to receive the $stageName decision."
}

function Wait-ForCamundaTasks(
    [string[]]$taskNames,
    [int]$baselineTaskCount,
    [string]$stageName,
    [System.Windows.Forms.TextBox]$outputBox
) {
    for ($attempt = 0; $attempt -lt 15; $attempt++) {
        $snapshot = Get-CommunicationSnapshot
        $newTaskLines = @(
            $snapshot.Lines |
                Where-Object { $_.Contains("[Camunda] Simulating") } |
                Select-Object -Skip $baselineTaskCount
        )
        $matchedLines = @()
        foreach ($taskName in $taskNames) {
            $taskLine = $newTaskLines |
                Where-Object { $_.Contains("Simulating $taskName for case") } |
                Select-Object -First 1
            if (-not $taskLine) {
                $matchedLines = @()
                break
            }
            $matchedLines += $taskLine
        }

        if ($matchedLines.Count -eq $taskNames.Count) {
            foreach ($line in $matchedLines) {
                $outputBox.AppendText("$line`r`n")
            }
            $outputBox.Refresh()
            Start-Sleep -Seconds 1
            return
        }

        Start-Sleep -Seconds 2
    }

    throw "Timed out waiting for Camunda to run $stageName."
}

$form = New-Object System.Windows.Forms.Form
$form.Text = "Preparedness Flow Test"
$form.StartPosition = "CenterScreen"
$form.ClientSize = New-Object System.Drawing.Size(760, 500)
$form.MinimumSize = New-Object System.Drawing.Size(650, 400)

$intro = New-Object System.Windows.Forms.Label
$intro.Location = New-Object System.Drawing.Point(16, 16)
$intro.Size = New-Object System.Drawing.Size(720, 42)
$intro.Text = "Runs randomized forecasts through INFORMATION, STATE, OPERATIONAL, then automatically clears the alert."
$form.Controls.Add($intro)

$runButton = New-Object System.Windows.Forms.Button
$runButton.Location = New-Object System.Drawing.Point(16, 68)
$runButton.Size = New-Object System.Drawing.Size(190, 34)
$runButton.Text = "Run full preparedness flow"
$form.Controls.Add($runButton)

$operateButton = New-Object System.Windows.Forms.Button
$operateButton.Location = New-Object System.Drawing.Point(218, 68)
$operateButton.Size = New-Object System.Drawing.Size(165, 34)
$operateButton.Text = "Open Camunda Operate"
$form.Controls.Add($operateButton)

$outputBox = New-Object System.Windows.Forms.TextBox
$outputBox.Location = New-Object System.Drawing.Point(16, 116)
$outputBox.Size = New-Object System.Drawing.Size(728, 366)
$outputBox.Anchor = "Top, Bottom, Left, Right"
$outputBox.Multiline = $true
$outputBox.ReadOnly = $true
$outputBox.ScrollBars = "Vertical"
$outputBox.WordWrap = $false
$outputBox.Font = New-Object System.Drawing.Font("Consolas", 9)
$form.Controls.Add($outputBox)

$operateButton.Add_Click({
    Start-Process "http://localhost:8081"
})

$runButton.Add_Click({
    $runButton.Enabled = $false
    $outputBox.Clear()

    try {
        $stamp = Get-Date -Format "yyyyMMddHHmmssfff"
        $locationId = "e2e-test-$stamp"

        $health = Invoke-RestMethod `
            -Uri "http://localhost:5001/health" `
            -TimeoutSec 5 `
            -ErrorAction Stop
        if ($health.status -ne "ok") {
            throw "Communication is not ready (health status: $($health.status))."
        }

        $seaLevelCm = Get-Random -Minimum 150 -Maximum 201
        $informationLeadHours = Get-Random -Minimum 5 -Maximum 7
        $stateLeadHours = Get-Random -Minimum 3 -Maximum 5
        $operationalLeadHours = Get-Random -Minimum 0 -Maximum 3

        $outputBox.AppendText("Location: $locationId`r`n")
        $outputBox.AppendText("Randomized sea level: $seaLevelCm cm (CATEGORY_2)`r`n")
        $outputBox.AppendText("Running staged alert decisions and automatic clear...`r`n`r`n")
        $outputBox.Refresh()

        $snapshot = Get-CommunicationSnapshot
        $refreshId = "e2e-$stamp-information"
        Send-TestRefresh $locationId $refreshId $seaLevelCm $informationLeadHours
        $outputBox.AppendText(
            "Sent INFORMATION forecast: $seaLevelCm cm at $informationLeadHours hours.`r`n"
        )
        $outputBox.Refresh()
        Wait-ForDecision $snapshot.DecisionCount "INFORMATION" $outputBox
        Wait-ForCamundaTasks `
            @("internalPreparedness", "informationPreparedness") `
            $snapshot.TaskCount "INFORMATION" $outputBox

        $snapshot = Get-CommunicationSnapshot
        $refreshId = "e2e-$stamp-state"
        Send-TestRefresh $locationId $refreshId $seaLevelCm $stateLeadHours
        $outputBox.AppendText(
            "Sent STATE forecast: $seaLevelCm cm at $stateLeadHours hours.`r`n"
        )
        $outputBox.Refresh()
        Wait-ForDecision $snapshot.DecisionCount "STATE" $outputBox
        Wait-ForCamundaTasks `
            @("staffPreparedness") `
            $snapshot.TaskCount "STATE" $outputBox

        $snapshot = Get-CommunicationSnapshot
        $refreshId = "e2e-$stamp-operational"
        Send-TestRefresh $locationId $refreshId $seaLevelCm $operationalLeadHours
        $outputBox.AppendText(
            "Sent OPERATIONAL forecast: $seaLevelCm cm at $operationalLeadHours hours.`r`n"
        )
        $outputBox.Refresh()
        Wait-ForDecision $snapshot.DecisionCount "OPERATIONAL" $outputBox
        Wait-ForCamundaTasks `
            @("operationalPreparedness") `
            $snapshot.TaskCount "OPERATIONAL" $outputBox

        $snapshot = Get-CommunicationSnapshot
        $refreshId = "e2e-$stamp-clear"
        Send-TestRefresh $locationId $refreshId 99 1
        $outputBox.AppendText("Sent NONE forecast: 99 cm at 1 hour to clear the alert.`r`n")
        $outputBox.Refresh()
        Wait-ForDecision $snapshot.DecisionCount "clear/NONE" $outputBox

        $outputBox.AppendText(
            "`r`nPASS: INFORMATION, STATE, OPERATIONAL, and NONE decisions were accepted; all preparedness tasks ran.`r`n"
        )
        $outputBox.AppendText(
            "The BPMN clear message was published. Open Operate to confirm the instance completed.`r`n"
        )
    } catch {
        $outputBox.AppendText("FULL FLOW TEST FAILED: $($_.Exception.Message)`r`n")
        $outputBox.AppendText("Check that the Docker Compose services are running and healthy.`r`n")
    } finally {
        $runButton.Enabled = $true
    }
})

[void]$form.ShowDialog()
