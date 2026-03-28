#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  ./ralph_loop.sh <prompt_name> [--max-loops N]

Arguments:
  prompt_name       Name of prompt file in prompts/ralph/<prompt_name>.md

Options:
  --max-loops N     Maximum loop iterations (default: 25)

Behavior:
  Runs a staged "Ralph loop" with opencode:
    1) Read SPEC.md
    2) Read/update todos/<prompt_name>.md (create if missing)
    3) Make plan for current todo item(s)
    4) Implement plan
    5) Review implementation + run tests + update todo statuses
    6) Commit and push git changes
EOF
}

if [[ $# -lt 1 ]]; then
  usage
  exit 1
fi

PROMPT_NAME="$1"
shift

MAX_LOOPS=25
while [[ $# -gt 0 ]]; do
  case "$1" in
    --max-loops)
      MAX_LOOPS="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SPEC_FILE="$SCRIPT_DIR/SPEC.md"
PROMPT_FILE="$SCRIPT_DIR/prompts/ralph/${PROMPT_NAME}.md"
TODO_DIR="$SCRIPT_DIR/todos"
TODO_FILE="$TODO_DIR/${PROMPT_NAME}.md"
PLAN_DIR="$SCRIPT_DIR/plans"
PLAN_FILE="$PLAN_DIR/${PROMPT_NAME}.md"

if [[ ! -f "$SPEC_FILE" ]]; then
  echo "Missing required file: $SPEC_FILE" >&2
  exit 1
fi

if [[ ! -f "$PROMPT_FILE" ]]; then
  # Common typo helper: intial -> initial
  PROMPT_NAME_FIX="${PROMPT_NAME/intial/initial}"
  PROMPT_FILE_FIX="$SCRIPT_DIR/prompts/ralph/${PROMPT_NAME_FIX}.md"
  if [[ "$PROMPT_NAME_FIX" != "$PROMPT_NAME" && -f "$PROMPT_FILE_FIX" ]]; then
    echo "Prompt not found for '${PROMPT_NAME}', using '${PROMPT_NAME_FIX}' instead."
    PROMPT_NAME="$PROMPT_NAME_FIX"
    PROMPT_FILE="$PROMPT_FILE_FIX"
    TODO_FILE="$TODO_DIR/${PROMPT_NAME}.md"
  fi
fi

if [[ ! -f "$PROMPT_FILE" ]]; then
  echo "Missing prompt file: $PROMPT_FILE" >&2
  echo "Available prompts:" >&2
  shopt -s nullglob
  for f in "$SCRIPT_DIR"/prompts/ralph/*.md; do
    echo "  - $(basename "${f%.md}")" >&2
  done
  shopt -u nullglob
  echo "Create it first, then rerun." >&2
  exit 1
fi

mkdir -p "$TODO_DIR"
mkdir -p "$PLAN_DIR"

if [[ ! -f "$TODO_FILE" ]]; then
  cat > "$TODO_FILE" <<EOF
# TODO - ${PROMPT_NAME}

- [ ] Read SPEC.md and extract constraints relevant to ${PROMPT_NAME}
- [ ] Break the requested work into concrete implementation tasks
- [ ] Implement next highest-priority task
- [ ] Review changes and run tests
EOF
  echo "Created todo file: $TODO_FILE"
fi

run_stage() {
  local stage_label="$1"
  local stage_instruction="$2"
  local continue_mode="$3"
  local agent_name="${4:-}"
  local current_loop="${5:-}"
  local max_loops="${6:-}"

  echo
  if [[ -n "$current_loop" && -n "$max_loops" ]]; then
    echo "===== Loop ${current_loop}/${max_loops} | ${stage_label} ====="
  else
    echo "===== ${stage_label} ====="
  fi

  local cmd=(opencode)
  #local cmd=(opencode -m github-copilot/gpt-5.3-codex)
  if [[ -n "$agent_name" ]]; then
    cmd+=(--agent "$agent_name")
  fi

  if [[ "$continue_mode" == "yes" ]]; then
    cmd+=(run --continue "$stage_instruction")
  else
    cmd+=(run "$stage_instruction")
  fi

  "${cmd[@]}"
}

has_open_todos() {
  grep -Eq '^- \[ \] ' "$TODO_FILE"
}

loop=1
while (( loop <= MAX_LOOPS )); do
  echo
  echo "######## Ralph Loop iteration ${loop}/${MAX_LOOPS} ########"

  run_stage \
    "Stage 1/6 - Read Spec" \
    "Read ${SPEC_FILE} and ${PROMPT_FILE} fully, then internalize all constraints before doing any implementation work." \
    "no" \
    "" \
    "$loop" \
    "$MAX_LOOPS"

  run_stage \
    "Stage 2/6 - Todo State" \
    "Read ${SPEC_FILE}, ${PROMPT_FILE}, and ${TODO_FILE}. Determine completed vs pending items and identify the next task(s). If needed, refine this todo file into actionable checklist items and preserve completed items." \
    "yes" \
    "" \
    "$loop" \
    "$MAX_LOOPS"

  run_stage \
    "Stage 3/6 - Plan Current Work" \
    "Read ${SPEC_FILE}, ${PROMPT_FILE}, and ${TODO_FILE}. Create a detailed implementation plan for the next pending todo item(s), then write it to ${PLAN_FILE}. Prefix the plan file with ${PROMPT_NAME} and keep scope tight and aligned with both spec and prompt." \
    "no" \
    "" \
    "$loop" \
    "$MAX_LOOPS"

  run_stage \
    "Stage 4/6 - Build" \
    "Read ${SPEC_FILE}, ${PROMPT_FILE}, and ${PLAN_FILE}. Implement the plan from ${PLAN_FILE} for current pending todo item(s). Update files in this repository and keep changes minimal and aligned with spec and prompt. After finishing a discrete feature/task from ${TODO_FILE}, run git add and create a commit when it is a sensible checkpoint." \
    "no" \
    "" \
    "$loop" \
    "$MAX_LOOPS"

  run_stage \
    "Stage 5/6 - Review and Test" \
    "Read ${SPEC_FILE}, ${PROMPT_FILE}, and ${TODO_FILE}. Review the implementation against ${TODO_FILE}, run relevant tests, then update ${TODO_FILE} by checking only truly completed items and leaving incomplete items unchecked." \
    "no" \
    "" \
    "$loop" \
    "$MAX_LOOPS"

  run_stage \
    "Stage 6/6 - Commit and Push" \
    "Check git status, commit all relevant changes with a clear message for ${PROMPT_NAME}, and push to the current branch. If there is nothing to commit, state that clearly and continue." \
    "no" \
    "" \
    "$loop" \
    "$MAX_LOOPS"

  if ! has_open_todos; then
    echo
    echo "All todo items are completed in ${TODO_FILE}. Stopping Ralph loop."
    exit 0
  fi

  loop=$((loop + 1))
done

echo
echo "Reached --max-loops (${MAX_LOOPS}) with pending todo items still present in ${TODO_FILE}."
exit 2
