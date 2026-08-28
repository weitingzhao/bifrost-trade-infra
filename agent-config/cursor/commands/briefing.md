Read the active briefing session pack and follow its instructions.

## Steps

1. Read the file `bifrost-platform/data/briefing/active-pack.md` — this is the session pack prepared by Ops Console.
2. Read the metadata file `bifrost-platform/data/briefing/active-meta.json` to confirm session_id, program_id, phase_id.
3. Follow the First-reply protocol specified in the pack header.
4. Use MCP `report_phase_progress` with the session_id from the pack to report progress.
5. When the phase defines `verify_cmd`, run it locally before reporting `status=done` with `verify_passed=true`.

## Important

- This pack was prepared by Ops Console (Bifrost Platform). Do NOT modify active-pack.md.
- If the file does not exist or is empty, inform the user: "No active briefing pack found. Prepare a session in Ops Console first."
- Follow all workspace rules (`.cursor/rules/`) and project CLAUDE.md files.
- Do not reuse this session_id for a different phase_id. To advance phases, MCP `create_session` with the new phase_id first.
