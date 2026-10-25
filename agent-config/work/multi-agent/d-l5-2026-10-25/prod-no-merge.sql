BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';
SET LOCAL TIME ZONE 'UTC';
LOCK TABLE agentrt.mission, agentrt.task, agentrt.attempt, agentrt.verification IN SHARE ROW EXCLUSIVE MODE;
DO $dl5$
BEGIN
  IF (SELECT md5(COALESCE(jsonb_agg(to_jsonb(x) ORDER BY x.mission_id), '[]'::jsonb)::text) FROM (SELECT mission_id,work_id,title,state,version,scope_json FROM agentrt.mission WHERE mission_id IN ('M-1','M-13','M-15','M-2','M-3','M-4')) x) IS DISTINCT FROM '9a8f921a8d4183babafeeb44698d5b00' THEN
    RAISE EXCEPTION 'D-L5 mission snapshot drift; rebuild approval';
  END IF;
  IF (SELECT md5(COALESCE(jsonb_agg(to_jsonb(x) ORDER BY x.task_id), '[]'::jsonb)::text) FROM (SELECT task_id,mission_id,role,title,repo,state,version,base_commit FROM agentrt.task WHERE mission_id IN ('M-1','M-13','M-15','M-2','M-3','M-4')) x) IS DISTINCT FROM '02dc7b3aec81e381c8186b55301f2c1e' THEN
    RAISE EXCEPTION 'D-L5 task snapshot drift; rebuild approval';
  END IF;
  IF (SELECT md5(COALESCE(jsonb_agg(to_jsonb(x) ORDER BY x.attempt_id), '[]'::jsonb)::text) FROM (SELECT a.attempt_id,a.task_id,a.attempt_no,a.state,a.pushed_ref,a.pushed_commit,a.ended_at FROM agentrt.attempt a JOIN agentrt.task t USING(task_id) WHERE t.mission_id IN ('M-1','M-13','M-15','M-2','M-3','M-4')) x) IS DISTINCT FROM '09d68a07cccfb322b8019fb00ddab33b' THEN
    RAISE EXCEPTION 'D-L5 attempt snapshot drift; rebuild approval';
  END IF;
  IF (SELECT md5(COALESCE(jsonb_agg(to_jsonb(x) ORDER BY x.verification_id), '[]'::jsonb)::text) FROM (SELECT v.verification_id,v.task_id,v.attempt_id,v.accepts_attempt,v.subject_commit,v.verdict,v.created_at FROM agentrt.verification v JOIN agentrt.task t USING(task_id) WHERE t.mission_id IN ('M-1','M-13','M-15','M-2','M-3','M-4')) x) IS DISTINCT FROM '34d3406230c5ffe5fdc26e055b0ca153' THEN
    RAISE EXCEPTION 'D-L5 verification snapshot drift; rebuild approval';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM agentrt.mission WHERE mission_id='M-1' AND version=2 AND scope_json='{"repos": ["bifrost-platform"], "max_action": "branch"}'::jsonb) THEN
    RAISE EXCEPTION 'D-L5 mission M-1 scope/version drift';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM agentrt.mission WHERE mission_id='M-13' AND version=2 AND scope_json='{"repos": ["bifrost-platform"], "max_action": "branch"}'::jsonb) THEN
    RAISE EXCEPTION 'D-L5 mission M-13 scope/version drift';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM agentrt.mission WHERE mission_id='M-15' AND version=2 AND scope_json='{"repos": ["bifrost-platform", "bifrost-trade-infra"], "max_action": "branch"}'::jsonb) THEN
    RAISE EXCEPTION 'D-L5 mission M-15 scope/version drift';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM agentrt.mission WHERE mission_id='M-2' AND version=3 AND scope_json='{"repos": ["bifrost-platform"], "max_action": "branch", "out_of_scope": ["The comment on GoalRepos in api/internal/agentrt/agentrtapi/goals.go (mission M-1).", "Adding a repository to Repos or changing any Verify or TestDirs value.", "Changing checkTest, planparse.go or any other code.", "Editing the comments on Repo, RepoNames, SpecTimeoutS or ImplementSpec."]}'::jsonb) THEN
    RAISE EXCEPTION 'D-L5 mission M-2 scope/version drift';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM agentrt.mission WHERE mission_id='M-3' AND version=2 AND scope_json='{"repos": ["bifrost-platform"], "max_action": "branch"}'::jsonb) THEN
    RAISE EXCEPTION 'D-L5 mission M-3 scope/version drift';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM agentrt.mission WHERE mission_id='M-4' AND version=3 AND scope_json='{"repos": ["bifrost-platform"], "max_action": "branch", "out_of_scope": ["Changing the behaviour of Go, Recover, Do or record.", "Rewording the package doc or the comments on Recover, Do or Contained.", "Adding or changing tests.", "Touching callers of safego.Go in other packages.", "Console or governance catalog changes."]}'::jsonb) THEN
    RAISE EXCEPTION 'D-L5 mission M-4 scope/version drift';
  END IF;
END;
$dl5$;
UPDATE agentrt.mission SET scope_json=jsonb_set(scope_json,'{no_merge}',to_jsonb('D-L5 / Work 565：历史演练结果已逐任务核对并归档；已处置、未交付，不合 main。归档 2026-10-25-work-565；原始对象及取消/被替代尝试保留。'::text),true), version=version+1 WHERE mission_id IN ('M-1','M-13','M-15','M-2','M-3','M-4');
SELECT mission_id,version,scope_json->>'no_merge' AS no_merge FROM agentrt.mission WHERE mission_id IN ('M-1','M-13','M-15','M-2','M-3','M-4') ORDER BY mission_id;
COMMIT;
