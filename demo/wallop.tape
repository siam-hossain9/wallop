# Hero GIF recipe — render with `vhs demo/wallop.tape` (https://github.com/charmbracelet/vhs)
# Captures one full chaos cycle: healthy -> latency creep -> error storm -> meltdown -> recovery.

Output docs/demo.gif

Set FontSize 16
Set Width 1280
Set Height 720
Set Theme "Dracula"
Set Padding 12
Set PlaybackSpeed 1.0

Hide
Type "uv run wallop demo -d 44 -c 40"
Show

Enter
Sleep 46s
