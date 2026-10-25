BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';
SET LOCAL TIME ZONE 'UTC';
LOCK TABLE agentrt.mission, agentrt.task, agentrt.attempt, agentrt.verification IN SHARE ROW EXCLUSIVE MODE;
DO $dl5$
BEGIN
  IF (SELECT md5(COALESCE(jsonb_agg(to_jsonb(x) ORDER BY x.mission_id), '[]'::jsonb)::text) FROM (SELECT mission_id,work_id,title,state,version,scope_json FROM agentrt.mission WHERE mission_id IN ('M-103','M-16','M-2','M-23','M-24','M-26','M-27')) x) IS DISTINCT FROM 'ffb6c7ff70fca818d889dfdfd0136a11' THEN
    RAISE EXCEPTION 'D-L5 mission snapshot drift; rebuild approval';
  END IF;
  IF (SELECT md5(COALESCE(jsonb_agg(to_jsonb(x) ORDER BY x.task_id), '[]'::jsonb)::text) FROM (SELECT task_id,mission_id,role,title,repo,state,version,base_commit FROM agentrt.task WHERE mission_id IN ('M-103','M-16','M-2','M-23','M-24','M-26','M-27')) x) IS DISTINCT FROM 'aa0e34971536830aba6751dd46e5c348' THEN
    RAISE EXCEPTION 'D-L5 task snapshot drift; rebuild approval';
  END IF;
  IF (SELECT md5(COALESCE(jsonb_agg(to_jsonb(x) ORDER BY x.attempt_id), '[]'::jsonb)::text) FROM (SELECT a.attempt_id,a.task_id,a.attempt_no,a.state,a.pushed_ref,a.pushed_commit,a.ended_at FROM agentrt.attempt a JOIN agentrt.task t USING(task_id) WHERE t.mission_id IN ('M-103','M-16','M-2','M-23','M-24','M-26','M-27')) x) IS DISTINCT FROM '65fa9b5609c68cbcf3709496b60e4d5b' THEN
    RAISE EXCEPTION 'D-L5 attempt snapshot drift; rebuild approval';
  END IF;
  IF (SELECT md5(COALESCE(jsonb_agg(to_jsonb(x) ORDER BY x.verification_id), '[]'::jsonb)::text) FROM (SELECT v.verification_id,v.task_id,v.attempt_id,v.accepts_attempt,v.subject_commit,v.verdict,v.created_at FROM agentrt.verification v JOIN agentrt.task t USING(task_id) WHERE t.mission_id IN ('M-103','M-16','M-2','M-23','M-24','M-26','M-27')) x) IS DISTINCT FROM 'fdf9035562ddde139f4c7616f860653f' THEN
    RAISE EXCEPTION 'D-L5 verification snapshot drift; rebuild approval';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM agentrt.mission WHERE mission_id='M-103' AND version=2 AND scope_json='{"repos": ["bifrost-trade-infra"], "max_action": "branch"}'::jsonb) THEN
    RAISE EXCEPTION 'D-L5 mission M-103 scope/version drift';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM agentrt.mission WHERE mission_id='M-16' AND version=2 AND scope_json='{"repos": ["bifrost-platform"], "max_action": "branch"}'::jsonb) THEN
    RAISE EXCEPTION 'D-L5 mission M-16 scope/version drift';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM agentrt.mission WHERE mission_id='M-2' AND version=2 AND scope_json='{"repos": ["bifrost-platform"], "max_action": "branch"}'::jsonb) THEN
    RAISE EXCEPTION 'D-L5 mission M-2 scope/version drift';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM agentrt.mission WHERE mission_id='M-23' AND version=2 AND scope_json='{"repos": ["bifrost-platform"], "max_action": "branch"}'::jsonb) THEN
    RAISE EXCEPTION 'D-L5 mission M-23 scope/version drift';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM agentrt.mission WHERE mission_id='M-24' AND version=2 AND scope_json='{"repos": ["bifrost-platform"], "max_action": "branch"}'::jsonb) THEN
    RAISE EXCEPTION 'D-L5 mission M-24 scope/version drift';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM agentrt.mission WHERE mission_id='M-26' AND version=2 AND scope_json='{"repos": ["bifrost-platform"], "max_action": "branch"}'::jsonb) THEN
    RAISE EXCEPTION 'D-L5 mission M-26 scope/version drift';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM agentrt.mission WHERE mission_id='M-27' AND version=2 AND scope_json='{"repos": ["bifrost-platform", "bifrost-trade-infra"], "max_action": "branch"}'::jsonb) THEN
    RAISE EXCEPTION 'D-L5 mission M-27 scope/version drift';
  END IF;
END;
$dl5$;
UPDATE agentrt.mission SET scope_json=jsonb_set(scope_json,'{no_merge}',to_jsonb('D-L5 / Work 565：历史演练结果已逐任务核对并归档；已处置、未交付，不合 main。归档 2026-10-25-work-565；原始对象及取消/被替代尝试保留。'::text),true), version=version+1 WHERE mission_id IN ('M-103','M-16','M-2','M-23','M-24','M-26','M-27');
SELECT mission_id,version,scope_json->>'no_merge' AS no_merge FROM agentrt.mission WHERE mission_id IN ('M-103','M-16','M-2','M-23','M-24','M-26','M-27') ORDER BY mission_id;
COMMIT;
