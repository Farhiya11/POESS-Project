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

$form = New-Object System.Windows.Forms.Form
$form.Text = "Preparedness Flow Test"
$form.StartPosition = "CenterScreen"
$form.ClientSize = New-Object System.Drawing.Size(760, 500)
$form.MinimumSize = New-Object System.Drawing.Size(650, 400)

$intro = New-Object System.Windows.Forms.Label
$intro.Location = New-Object System.Drawing.Point(16, 16)
$intro.Size = New-Object System.Drawing.Size(720, 42)
$intro.Text = "Sends a randomized, in-range forecast to Siddhi and checks whether communication started the BPMN preparedness flow."
$form.Controls.Add($intro)

$runButton = New-Object System.Windows.Forms.Button
$runButton.Location = New-Object System.Drawing.Point(16, 68)
$runButton.Size = New-Object System.Drawing.Size(170, 34)
$runButton.Text = "Run preparedness test"
$form.Controls.Add($runButton)

$operateButton = New-Object System.Windows.Forms.Button
$operateButton.Location = New-Object System.Drawing.Point(198, 68)
$operateButton.Size = New-Object System.Drawing.Size(145, 34)
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
        $refreshId = "e2e-$stamp"

        $health = Invoke-RestMethod `
            -Uri "http://localhost:5001/health" `
            -TimeoutSec 5 `
            -ErrorAction Stop
        if ($health.status -ne "ok") {
            throw "Communication is not ready (health status: $($health.status))."
        }

        $baselineLogs = Get-CommunicationLogs
        $baselineDecisionCount = @(
            ($baselineLogs -split "`r?`n") |
                Where-Object { $_ -match 'POST /preparedness_decision HTTP/1\.1" \d{3}' }
        ).Count

        $category1MinCm = 100
        $category2MinCm = 150
        $category3AboveCm = 200
        $forecastHorizonHours = 36
        $informationLeadHours = 6
        $stateLeadHours = 4
        $operationalLeadHours = 2
        $maximumSeaLevelCm = 250
        $seaLevelCm = Get-Random -Minimum $category1MinCm -Maximum ($maximumSeaLevelCm + 1)
        $leadTimeHours = Get-Random -Minimum 0 -Maximum ($forecastHorizonHours + 1)

        if ($seaLevelCm -gt $category3AboveCm) {
            $warningCategory = "CATEGORY_3"
        } elseif ($seaLevelCm -ge $category2MinCm) {
            $warningCategory = "CATEGORY_2"
        } else {
            $warningCategory = "CATEGORY_1"
        }

        if ($leadTimeHours -le $operationalLeadHours) {
            $alertLevel = "OPERATIONAL"
        } elseif ($leadTimeHours -le $stateLeadHours) {
            $alertLevel = "STATE"
        } elseif ($leadTimeHours -le $informationLeadHours) {
            $alertLevel = "INFORMATION"
        } else {
            $alertLevel = "INTERNAL"
        }

        $policy = @{
            forecast_horizon_hours = $forecastHorizonHours
            information_lead_hours = $informationLeadHours
            state_lead_hours = $stateLeadHours
            operational_lead_hours = $operationalLeadHours
            regions = @{
                "test-region" = @{
                    category_1_min_cm = $category1MinCm
                    category_2_min_cm = $category2MinCm
                    category_3_above_cm = $category3AboveCm
                }
            }
            locations = @{}
        }
        $policy.locations[$locationId] = @{ region = "test-region" }

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

        $outputBox.AppendText("Refresh accepted by Siddhi.`r`n")
        $outputBox.AppendText("Refresh ID: $refreshId`r`n")
        $outputBox.AppendText("Location:   $locationId`r`n")
        $outputBox.AppendText("Forecast:   $seaLevelCm cm at $leadTimeHours hours`r`n")
        $outputBox.AppendText("Expected:   $alertLevel / $warningCategory`r`n`r`n")
        $outputBox.AppendText("Checking communication and Camunda logs...`r`n")

        try {
            $logLines = @()
            $decisionLine = $null
            $decisionStatus = $null
            $taskLines = @()
            for ($attempt = 0; $attempt -lt 8 -and $taskLines.Count -eq 0; $attempt++) {
                $logs = Get-CommunicationLogs
                $logLines = @($logs -split "`r?`n")
                $decisionLine = $null
                $decisionStatus = $null
                $decisionIndex = -1
                $decisionCount = 0

                for ($lineIndex = 0; $lineIndex -lt $logLines.Count; $lineIndex++) {
                    if ($logLines[$lineIndex] -match 'POST /preparedness_decision HTTP/1\.1" (\d{3})') {
                        $decisionCount++
                        if ($decisionCount -gt $baselineDecisionCount) {
                            $decisionLine = $logLines[$lineIndex]
                            $decisionStatus = $Matches[1]
                            $decisionIndex = $lineIndex
                        }
                    }
                }

                if ($decisionStatus -eq "200" -and $decisionIndex -ge 0) {
                    for ($lineIndex = $decisionIndex + 1; $lineIndex -lt $logLines.Count; $lineIndex++) {
                        if ($logLines[$lineIndex].Contains("[Camunda] Simulating")) {
                            $taskLines += $logLines[$lineIndex]
                        }
                    }
                }

                if ($taskLines.Count -eq 0 -and $decisionStatus -notin @("400", "503")) {
                    Start-Sleep -Seconds 2
                }
            }

            if ($decisionStatus -eq "200" -and $taskLines.Count -gt 0) {
                $outputBox.AppendText("PASS: communication accepted the decision and Camunda ran preparedness tasks.`r`n")
                $outputBox.AppendText("$decisionLine`r`n")
                foreach ($line in $taskLines) {
                    $outputBox.AppendText("$line`r`n")
                }
            } else {
                $outputBox.AppendText("The Siddhi request was accepted, but Camunda execution was not confirmed.`r`n")
                if ($decisionLine) {
                    $outputBox.AppendText("$decisionLine`r`n")
                }
                $relevantLines = $logLines |
                    Where-Object {
                        $_.Contains("/preparedness_decision") -or
                        $_.Contains("ERROR") -or
                        $_.Contains("Error")
                    }
                foreach ($line in $relevantLines) {
                    $outputBox.AppendText("$line`r`n")
                }
                $outputBox.AppendText("You can inspect the complete recent logs with the Docker Desktop interface.`r`n")
            }
        } catch {
            $outputBox.AppendText("The request succeeded, but communication logs could not be read.`r`n")
            $outputBox.AppendText("$($_.Exception.Message)`r`n")
        }
    } catch {
        $outputBox.AppendText("TEST FAILED: $($_.Exception.Message)`r`n")
        $outputBox.AppendText("Check that the Docker Compose services are running and healthy.`r`n")
    } finally {
        $runButton.Enabled = $true
    }
})

[void]$form.ShowDialog()
