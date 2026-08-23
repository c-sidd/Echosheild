# frontend/fetch-assets.ps1 - Run once before demo
New-Item -ItemType Directory -Force public\assets | Out-Null
$texUrl = "https://raw.githubusercontent.com/mrdoob/three.js/dev/examples/textures/waternormals.jpg"
Invoke-WebRequest $texUrl -OutFile "public\assets\waternormals.jpg"
Write-Output "Assets downloaded."
