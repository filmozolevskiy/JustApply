#!/bin/bash
set -e

usage() {
  cat <<EOF
Usage: $0 -p <prd> [options]

Required:
  -p <prd>       Parent PRD issue number or GitHub issue URL

Options:
  -a <agent>     Agent to run: gemini (default) or claude
  -i <n>         Max iterations (default: 10)
  -s <skill>     Skill name under ~/.claude/skills or ~/.gemini/config/skills
  -v             Stream Claude tool calls and progress (claude agent only; uses
                 --verbose --output-format=stream-json, formatted with jq)
  -h             Show this help

Example:
  unset GITHUB_TOKEN && $0 -p 68 -a claude -s tdd -i 8 -v
EOF
}

# Default values
AGENT="gemini"
ITERATIONS=10
SKILL=""
PRD=""
VERBOSE=0

# Parse flags
while getopts "a:i:s:p:vh" opt; do
  case $opt in
    a) AGENT="$OPTARG" ;;
    i) ITERATIONS="$OPTARG" ;;
    s) SKILL="$OPTARG" ;;
    p) PRD="$OPTARG" ;;
    v) VERBOSE=1 ;;
    h) usage && exit 0 ;;
    *) usage && exit 1 ;;
  esac
done

if [ -z "$PRD" ]; then
  echo "Error: -p <prd> is required." && exit 1
fi

# Extract numeric ID if a full URL was provided
PRD_NUMBER=$(echo "$PRD" | grep -o -E '[0-9]+$' || echo "$PRD")

# Initialize and clear progress.txt for a clean run
echo "# Ralph Loop Progress Log" > progress.txt

# Base prompt instructing the agent on GitHub Issues workflow
BASE_PROMPT="You are implementing tasks for Parent PRD #$PRD_NUMBER.

1. Read progress.txt to see what has already been done in previous iterations.
2. Use the gh CLI to list open issues labeled 'ready-for-agent'.
3. Select the highest priority issue that references Parent PRD #$PRD_NUMBER.
4. Print the issue number and title wrapped in <task>Issue Title (#Number)</task> tags.
5. Implement the task.
6. Run tests.
7. Append a summary of what you implemented in this iteration to progress.txt.
8. Commit your changes (including the updated progress.txt).
9. Close the issue on GitHub when complete.
10. If no open 'ready-for-agent' issues referencing Parent PRD #$PRD_NUMBER remain, output <promise>COMPLETE</promise>.
11. ONLY WORK ON A SINGLE TASK."

# Agent config — single place to add new agents
case "$AGENT" in
  gemini)
    CMD_TEMPLATE='agy --dangerously-skip-permissions -p {prompt}'
    SKILLS_DIR="$HOME/.gemini/config/skills" ;;
  claude)
    CLAUDE_EXTRA=""
    if [ "$VERBOSE" -eq 1 ]; then
      # --verbose alone does not stream in -p mode; stream-json requires --verbose.
      CLAUDE_EXTRA="--verbose --output-format=stream-json "
    fi
    CMD_TEMPLATE="claude --dangerously-skip-permissions ${CLAUDE_EXTRA}-p {prompt} < /dev/null"
    SKILLS_DIR="$HOME/.claude/skills" ;;
  *)
    echo "Unknown agent: $AGENT" && exit 1 ;;
esac

# Append skill to prompt if specified
if [ -n "$SKILL" ]; then
  SKILL_PATH="$SKILLS_DIR/$SKILL/SKILL.md"
  if [ -f "$SKILL_PATH" ]; then
    BASE_PROMPT="${BASE_PROMPT}

Additional Skill Instructions:
$(cat "$SKILL_PATH")"
  else
    echo "Warning: $SKILL_PATH not found."
  fi
fi

# Escape prompt to make it safe inside single quotes
ESCAPED_PROMPT=$(echo -n "$BASE_PROMPT" | sed "s/'/'\\\\''/g")

# Replace {prompt} with single-quoted escaped prompt
FINAL_CMD="${CMD_TEMPLATE//\{prompt\}/'$ESCAPED_PROMPT'}"

# ANSI color codes for terminal readability
COLOR_ITERATION="\033[1;35m" # Bold Magenta
COLOR_TASK="\033[1;36m"      # Bold Cyan
COLOR_RESET="\033[0m"

if [ "$VERBOSE" -eq 1 ] && [ "$AGENT" != "claude" ]; then
  echo "Warning: -v applies to the claude agent only; ignored for $AGENT."
fi

VERBOSE_LABEL=""
if [ "$VERBOSE" -eq 1 ] && [ "$AGENT" = "claude" ]; then
  if ! command -v jq >/dev/null 2>&1; then
    echo "Error: -v requires jq (brew install jq)." && exit 1
  fi
  VERBOSE_LABEL=", verbose on (stream-json)"
fi

echo "Starting Ralph Loop ($ITERATIONS iterations max) using agent: $AGENT${VERBOSE_LABEL}"

# Human-readable stream from Claude print-mode NDJSON (raw JSON still tee'd for parsing).
CLAUDE_STREAM_JQ='select(.type == "assistant") | .message.content[] |
  if .type == "text" then .text
  elif .type == "tool_use" then "[Tool: \(.name)] \(.input | tostring)"
  else empty end'

for ((i=1; i<=ITERATIONS; i++)); do
  echo -e "\n${COLOR_ITERATION}=== Iteration $i of $ITERATIONS ===${COLOR_RESET}\n"
  
  # Stream output to terminal and capture it
  TMPFILE=$(mktemp)
  if [ "$VERBOSE" -eq 1 ] && [ "$AGENT" = "claude" ]; then
    if command -v unbuffer >/dev/null 2>&1; then
      unbuffer bash -c "$FINAL_CMD" 2>&1 | tee "$TMPFILE" | jq -r --unbuffered "$CLAUDE_STREAM_JQ"
    else
      eval "$FINAL_CMD" 2>&1 | tee "$TMPFILE" | jq -r --unbuffered "$CLAUDE_STREAM_JQ"
    fi
  elif command -v unbuffer >/dev/null 2>&1; then
    unbuffer bash -c "$FINAL_CMD" 2>&1 | tee "$TMPFILE"
  else
    eval "$FINAL_CMD" 2>&1 | tee "$TMPFILE"
  fi
  OUTPUT=$(cat "$TMPFILE")
  rm -f "$TMPFILE"
  
  # Extract active task from output
  CURRENT_TASK=$(echo "$OUTPUT" | grep -o -E '<task>[^<]*</task>' | sed -e 's/<task>//' -e 's/<\/task>//' | head -n 1)
  if [ -n "$CURRENT_TASK" ]; then
    echo -e "\n${COLOR_TASK}>>> Agent worked on: $CURRENT_TASK${COLOR_RESET}\n"
  fi
  
  # Check for completion sigil
  if [[ "$OUTPUT" == *"<promise>COMPLETE</promise>"* ]]; then
    echo "PRD complete after $i iterations."
    exit 0
  fi
done

echo "Finished $ITERATIONS iterations."
