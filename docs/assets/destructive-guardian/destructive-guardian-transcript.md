# Destructive Guardian demonstration transcript

0-4 seconds: This is an automated replay from the verified public capture, not a live screen recording. The same harmless command appears in both terminals.

4-9 seconds: The terminal titled "Without the guard" replays the unprotected result. `GUARD_INACTIVE_PROOF` prints. The missing `destructive-guardian-self-test` sentinel returns the shell error and exit 127.

9-16 seconds: The terminal titled "With the guard" shows `Agent -> PreToolUse guard -> Shell`. The guard stops the tool call before the shell.

16-25 seconds: The exact denial is `Destructive Guardian self-test denied before Bash execution.` The capture has zero protected `command_execution` events and no marker output.

25-28 seconds: Skills are the Instruction Layer. Hooks and guards are the Enforcement Layer.

There is no voice and no audio track.
