"""Round-7 rulings.

EQUIVALENT: the probe saw the mutated value differ, and publish_total bytes matched.
UNREACHABLE: an earlier check makes the differing value impossible; that check is file:line.
Each sentence names the mutated expression at its own line.
"""

EQUIVALENT = {
    'contextual.py:_apply:103:8:guard_pass:0': 'In _apply at line 103, `return` and `pass` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'contextual.py:_apply:115:8:guard_pass:0': 'In _apply at line 115, `return` and `pass` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'contextual.py:_apply:146:8:guard_pass:0': 'In _apply at line 146, `return` and `pass` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'contextual.py:_apply:157:8:guard_pass:0': 'In _apply at line 157, `return` and `pass` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'contextual.py:_apply:168:8:guard_pass:0': 'In _apply at line 168, `return` and `pass` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'contextual.py:_apply:171:8:guard_pass:0': 'In _apply at line 171, `return` and `pass` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'contextual.py:_apply:38:8:guard_pass:0': 'In _apply at line 38, `return` and `pass` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'contextual.py:_apply:43:8:guard_pass:0': 'In _apply at line 43, `return` and `pass` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'contextual.py:_apply:70:8:guard_pass:0': 'In _apply at line 70, `return` and `pass` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'contextual.py:_apply:75:8:guard_pass:0': 'In _apply at line 75, `return` and `pass` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'contextual.py:_apply:83:8:guard_pass:0': 'In _apply at line 83, `return` and `pass` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'contextual.py:_apply:97:8:guard_pass:0': 'In _apply at line 97, `return` and `pass` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'contextual.py:_contextual:184:11:compare:0': 'In _contextual at line 184, `index != 0` and `index == 0` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'contextual.py:_contextual:184:11:operand:0': "In _contextual at line 184, `index != 0 and event.get('seq') != 1` and `event.get('seq') != 1` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.",
    'contextual.py:_contextual:184:20:constant:4': 'In _contextual at line 184, `0` and `-1` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'contextual.py:_contextual:184:20:constant:5': 'In _contextual at line 184, `0` and `1` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'contextual.py:_contextual:184:26:compare:0': "In _contextual at line 184, `event.get('seq') != 1` and `event.get('seq') == 1` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.",
    'contextual.py:_contextual:184:46:constant:13': 'In _contextual at line 184, `1` and `2` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'contextual.py:_contextual:185:12:guard_pass:0': "In _contextual at line 185, `return 'not_first'` and `pass` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.",
    'fold.py:_base:320:7:operand:0': 'In _base at line 320, `step.superseded and step.by_step` and `step.by_step` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'fold.py:_base:320:7:operand:1': 'In _base at line 320, `step.superseded and step.by_step` and `step.superseded` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'fold.py:_base:322:4:negate:0': "In _base at line 322, `if step.superseded_text is not None: public['superseded_text'] = step.superseded_text` and `if not step.superseded_text is not None: public['superseded_text'] = step.superseded_text` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.",
    'fold.py:_base:322:7:compare:0': 'In _base at line 322, `step.superseded_text is not None` and `step.superseded_text is None` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'fold.py:_feed:267:12:operand:0': "In _feed at line 267, `event.get('by') or ''` and `''` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.",
    'fold.py:_feed:277:56:operand:0': "In _feed at line 277, `event.get('by') or ''` and `''` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.",
    'fold.py:_feed:281:12:guard_pass:0': 'In _feed at line 281, `continue` and `pass` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'fold.py:_feed:285:46:operand:0': "In _feed at line 285, `event.get('by') or ''` and `''` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.",
    'fold.py:_record_last_seen:563:4:negate:0': "In _record_last_seen at line 563, `if latest.get('found') is False: ref_state = 'not_found' else: ref_state = 'found'` and `if not latest.get('found') is False: ref_state = 'not_found' else: ref_state = 'found'` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.",
    'fold.py:_record_last_seen:563:9:compare:0': "In _record_last_seen at line 563, `latest.get('found') is False` and `latest.get('found') is not False` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.",
    'fold.py:_record_step:521:11:compare:0': 'In _record_step at line 521, `last is not None` and `last is None` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'fold.py:_record_step:521:8:negate:0': "In _record_step at line 521, `if last is not None: public['last_seen'] = last` and `if not last is not None: public['last_seen'] = last` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.",
    'fold.py:_unknown:475:19:operand:1': "In _unknown at line 475, `row or 'unknown'` and `row` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.",
    'fold.py:_waiting_on_open:572:8:guard_pass:0': 'In _waiting_on_open at line 572, `return False` and `pass` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'ownerball.py:_in_flight_since:410:11:operand:1': "In _in_flight_since at line 410, `status is None or status.get('status') != 'in_flight'` and `status is None` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.",
    'ownerball.py:_in_flight_since:411:12:guard_pass:0': 'In _in_flight_since at line 411, `continue` and `pass` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'ownerball.py:_not_yet_since:437:11:operand:1': "In _not_yet_since at line 437, `status and status.get('status') == 'not_yet'` and `status` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.",
    'ownerball.py:_owner_since:422:11:operand:1': "In _owner_since at line 422, `status is None or status.get('status') != 'yes'` and `status is None` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.",
    'ownerball.py:_owner_since:423:12:guard_pass:0': 'In _owner_since at line 423, `continue` and `pass` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'ownerball.py:_owner_since:426:12:guard_pass:0': 'In _owner_since at line 426, `continue` and `pass` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'ownerball.py:_owner_sort:57:25:constant:10': "In _owner_sort at line 57, `'record'` and `'recor'` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.",
    'ownerball.py:_owner_sort:57:25:constant:11': "In _owner_sort at line 57, `'record'` and `'record~'` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.",
    'ownerball.py:_owner_sort:58:14:operand:0': "In _owner_sort at line 58, `item.get('ref') or {}` and `{}` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.",
    'ownerball.py:_owner_sort:59:17:operand:0': "In _owner_sort at line 59, `ref.get('kind') or ''` and `''` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.",
    'ownerball.py:_owner_sort:59:40:operand:0': "In _owner_sort at line 59, `ref.get('id') or ''` and `''` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.",
    'ownerball.py:_owner_sort:61:17:operand:0': "In _owner_sort at line 61, `item.get('works') or [{}]` and `[{}]` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.",
    'ownerball.py:_owner_sort:62:17:operand:0': "In _owner_sort at line 62, `piece.get('work_id') or ''` and `''` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.",
    'ownerball.py:_pick:303:7:operand:1': "In _pick at line 303, `times and holder != 'unknown'` and `times` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.",
    'ownerball.py:_streak_start:367:39:constant:8': 'In _streak_start at line 367, `0` and `-1` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'publish.py:_finite_number:734:7:compare:0': 'In _finite_number at line 734, `type(value) is float` and `type(value) is not float` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'publish.py:_no_null:741:8:guard_pass:0': 'In _no_null at line 741, `return False` and `pass` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'publish.py:_trim_owner:395:7:compare:0': 'In _trim_owner at line 395, `len(items) <= PUBLISH_MAX_OWNER_ALL` and `len(items) < PUBLISH_MAX_OWNER_ALL` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'read.py:_int_token:276:12:guard_pass:0': 'In _int_token at line 276, `return None` and `pass` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'read.py:_norm:299:8:guard_pass:0': 'In _norm at line 299, `return {key: _norm(child) for key, child in value.items()}` and `pass` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'read.py:_norm:301:8:guard_pass:0': 'In _norm at line 301, `return [_norm(child) for child in value]` and `pass` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'read.py:_token_bad:233:17:constant:6': "In _token_bad at line 233, `'-0'` and `'-'` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.",
    'read.py:_token_bad:233:17:constant:7': "In _token_bad at line 233, `'-0'` and `'-0~'` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.",
    'read.py:_token_bad:233:23:constant:8': "In _token_bad at line 233, `'-0.0'` and `'-0.'` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.",
    'read.py:_token_bad:233:23:constant:9': "In _token_bad at line 233, `'-0.0'` and `'-0.0~'` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.",
    'read.py:_token_bad:234:8:guard_pass:0': 'In _token_bad at line 234, `return False` and `pass` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'read.py:_token_bad:236:24:constant:11': 'In _token_bad at line 236, `17` and `18` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'read.py:_token_bad:237:12:guard_pass:0': 'In _token_bad at line 237, `return True` and `pass` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'read.py:class_name:127:7:operand:0': 'In class_name at line 127, `type(name) is str and _CLASS.fullmatch(name)` and `_CLASS.fullmatch(name)` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'read.py:class_name:127:7:operand:1': 'In class_name at line 127, `type(name) is str and _CLASS.fullmatch(name)` and `type(name) is str` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'read.py:prescan:307:7:compare:0': "In prescan at line 307, `body.count(b'[') + body.count(b'{') <= MAX_DEPTH` and `body.count(b'[') + body.count(b'{') < MAX_DEPTH` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.",
    'read.py:prescan:308:8:guard_pass:0': 'In prescan at line 308, `return None` and `pass` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'read.py:prescan:325:15:compare:0': 'In prescan at line 325, `depth > MAX_DEPTH` and `depth >= MAX_DEPTH` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'read.py:read_line:372:49:constant:4': 'In read_line at line 372, `0` and `-1` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'read.py:read_log:443:24:compare:0': 'In read_log at line 443, `cut < 0` and `cut <= 0` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'read.py:read_log:443:30:constant:4': 'In read_log at line 443, `0` and `-1` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'read.py:read_log:443:30:constant:5': 'In read_log at line 443, `0` and `1` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'read.py:read_log:446:8:guard_pass:0': 'In read_log at line 446, `return out` and `pass` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'read.py:read_log:467:11:operand:0': "In read_log at line 467, `parsed.kind != 'break' and parsed.digest` and `parsed.digest` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.",
    'read.py:read_log:467:11:operand:1': "In read_log at line 467, `parsed.kind != 'break' and parsed.digest` and `parsed.kind != 'break'` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.",
    'read.py:read_log:467:26:constant:8': "In read_log at line 467, `'break'` and `'brea'` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.",
    'read.py:read_log:467:26:constant:9': "In read_log at line 467, `'break'` and `'break~'` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.",
    'validate.py:_fields:459:11:operand:1': "In _fields at line 459, `not isinstance(event['confirmed'], list) or not isinstance(event['failed'], list)` and `not isinstance(event['confirmed'], list)` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.",
    'validate.py:_locator:512:34:compare:0': 'In _locator at line 512, `key not in allowed` and `key in allowed` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'validate.py:_seq_of:224:4:negate:0': "In _seq_of at line 224, `if isinstance(event, (dict, Event)): seq = event.get('seq') if is_int(seq): return seq` and `if not isinstance(event, (dict, Event)): seq = event.get('seq') if is_int(seq): return seq` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.",
    'validate.py:_seq_of:226:8:negate:0': 'In _seq_of at line 226, `if is_int(seq): return seq` and `if not is_int(seq): return seq` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'validate.py:_seq_of:227:12:guard_pass:0': 'In _seq_of at line 227, `return seq` and `pass` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.',
    'validate.py:parse_event:238:8:guard_pass:0': "In parse_event at line 238, `return (None, 'bad_type')` and `pass` take different values under the round-7 checks, and publish_total stays byte-identical because this branch does not change the folded document.",
    'redact_bound.py:string_growth:30:7:operand:1': 'In string_growth at line 30, dropping the empty-string disjunct leaves only the type check, which is false for "", and the growth of an empty string is still 0.',
    'redact_bound.py:string_growth:30:40:constant:5': 'In string_growth at line 30, `text == ""` and `text == "~"` differ for an empty string, and that string still contributes no growth.',
    'redact_bound.py:growth:51:16:negate:0': 'In growth at line 51, negating the string-key check measures a non-string key, and string_growth of a non-string is 0.',
    'redact_bound.py:growth:51:19:compare:0': 'In growth at line 51, `type(key) is str` and `type(key) is not str` differ for an integer key, and string_growth of that key is 0.',
    'fold.py:_finish:356:7:operand:0': "In _finish at line 356, dropping the `'signal' in exit_body` check leaves get('signal'), which is None when the key is absent, and a missing signal still falls through to the exit code.",
    'contextual.py:_apply:162:8:guard_pass:0': 'In _apply at line 162, `return` and `pass` differ after owner_wait_ready, and no later kind matches that event, so can_act and yes_at stay set.',
    'contextual.py:_apply:174:8:guard_pass:0': 'In _apply at line 174, `return` and `pass` differ after observer_round, and that branch is last, so the round stays appended.',
    'ownerball.py:_effect:97:7:operand:1': 'In _effect at line 97, dropping `step.usual_s is None` leaves `step is None`, which is false for a step whose usual time is missing, and the returned usual time is still None.',
    'ownerball.py:_judge_work:348:7:operand:1': 'In _judge_work at line 348, `pending and all(...)` and `pending` differ for a not-yet item, and every item that reaches that line is not_yet so the same ball is returned.',
    'ownerball.py:_merged_record:173:69:operand:1': 'In _merged_record at line 173, `reason or "not_confirmed"` and `reason` differ when the confirm reason is None, and _unknown_record_item stores not_confirmed for any reason outside the closed set.',
    'publish.py:_level1:220:12:guard_pass:0': 'In _level1 at line 220, `continue` and `pass` differ on a summary, and a summary has no steps for the following loop to strip.',
    'publish.py:_level6:294:9:operand:0': 'In _level6 at line 294, dropping the `owner_all_cut` membership check leaves `not prior`, and popping an absent key leaves the document unchanged.',
    'publish.py:publish_view:93:40:compare:0': 'In publish_view at line 93, `len(original_feed) > feed_cap` and `>=` differ when the feed is exactly at the cap, and the last cap rows are the whole feed.',
    'read.py:Folded.__init__:87:11:compare:0': 'In Folded.__init__ at line 87, `token is _FOLD_TOKEN` and `token is not _FOLD_TOKEN` differ for an ordinary call, and `or True` still raises TypeError.',
    'read.py:Folded.__init__:87:35:compare:0': 'In Folded.__init__ at line 87, `document is not None` and `document is None` differ when a document is passed, and `or True` still raises TypeError.',
    'read.py:_in_range:137:12:guard_pass:0': 'In _in_range at line 137, `return False` and `pass` differ for nan, and the following range comparison is also false for nan.',
    'read.py:_int_token:271:11:operand:0': 'In _int_token at line 271, dropping the `.eE` disjunct leaves `len(token) > 17`, which is false for "1.5", and int("1.5") still returns None.',
    'read.py:_is_folded:108:8:guard_pass:0': 'In _is_folded at line 108, `return False` and `pass` differ for an ordinary object, and `_held(value) is not None` is also false.',
    'read.py:_token_bad:247:7:operand:1': 'In _token_bad at line 247, dropping the infinity disjunct leaves `number != number`, which is false for "1e999", and abs(inf) is still above 2**53.',
    'read.py:_token_bad:248:8:guard_pass:0': 'In _token_bad at line 248, `return True` and `pass` differ for "1e999", and the following abs(inf) comparison is also true.',
    'read.py:exact_tree:184:15:operand:1': 'In exact_tree at line 184, dropping the cycle check leaves `depth > MAX_DEPTH`, which is false on the first revisit, and following the cycle then exceeds the depth.',
    'read.py:at_or_0:144:11:operand:0': 'In at_or_0 at line 144, dropping `type(now) is float` leaves `now == 0`, which is true for the integer 0, and the returned time is still 0.',
    'read.py:read_log:466:15:operand:1': 'In read_log at line 466, `parsed.digest or prev` and `parsed.digest` differ when a later break has an empty digest, and that break ends the log before the new prev is read.',
    'validate.py:_backwards:688:29:compare:0': 'In _backwards at line 688, `at > max_at` and `at >= max_at` differ when at equals the maximum, and assigning that same maximum changes no later threshold.',
}

UNREACHABLE = {
    'contextual.py:_contextual:184:11:operand:1': 'read.py:401',
    'contextual.py:_contextual:184:36:constant:4': 'read.py:401',
    'contextual.py:_contextual:184:36:constant:5': 'read.py:401',
    'contextual.py:_contextual:184:46:constant:12': 'read.py:401',
    'contextual.py:_contextual:193:12:guard_pass:0': 'contextual.py:179',
    'fold.py:_eta_unsure:221:33:constant:8': 'fold.py:219',
    'fold.py:_eta_unsure:221:33:constant:9': 'fold.py:219',
    # gap_flag is {3: SUMMARY_GAP_3, 5: SUMMARY_GAP_5, 6: SUMMARY_GAP_6}.get(level, 0).
    # Those three module constants are 0, so the conjunction at line 162 is dead.
    'survive.py:apply_keep:162:11:operand:1': 'constant:survive.SUMMARY_GAP_3+survive.SUMMARY_GAP_5+survive.SUMMARY_GAP_6=0',
    'survive.py:apply_keep:162:24:compare:0': 'constant:survive.SUMMARY_GAP_3+survive.SUMMARY_GAP_5+survive.SUMMARY_GAP_6=0',
    'survive.py:apply_keep:162:24:constant:0': 'constant:survive.SUMMARY_GAP_3+survive.SUMMARY_GAP_5+survive.SUMMARY_GAP_6=0',
    'survive.py:apply_keep:162:24:constant:1': 'constant:survive.SUMMARY_GAP_3+survive.SUMMARY_GAP_5+survive.SUMMARY_GAP_6=0',
    # nan has no '.', 'e', or 'E', so it returns from the integer branch and
    # `number != number` never takes a different value.
    'read.py:_token_bad:247:7:operand:0': 'read.py:235',
    # APPROVAL_TERMINAL ⊆ APPROVAL_STATES, so dropping the states conjunct
    # cannot change the conjunction. Same for questions.
    'model.py:terminal_state:438:15:operand:0': 'subset:model.APPROVAL_TERMINAL<=model.APPROVAL_STATES',
    'model.py:terminal_state:440:15:operand:0': 'subset:model.QUESTION_TERMINAL<=model.QUESTION_STATES',
    # `or True` makes the other disjuncts unable to change the condition.
    # operand:2 on this line is killed by Folded().
    'read.py:Folded.__init__:87:11:operand:0': 'read.py:87',
    'read.py:Folded.__init__:87:11:operand:1': 'read.py:87',
    # ±inf already fail -TWO53..TWO53, so dropping one infinity conjunct cannot
    # change the conjunction. A comparison mutant on this line is killed.
    'read.py:_in_range:138:15:operand:0': 'read.py:138',
    'read.py:_in_range:138:15:operand:1': 'read.py:138',
    # _bad_string already returns true for a non-string. That return is killed.
    'read.py:exact_tree:190:23:operand:0': 'read.py:152',
    # Only a dict or a list is stacked. The leaf return at the entry is killed.
    'read.py:exact_tree:197:16:guard_pass:0': 'read.py:178',
    # _in_range returns false unless the value is an int or a float.
    'read.py:at_or_0:143:7:operand:0': 'read.py:133',
    # A bool is neither int nor float, so the bool disjunct cannot change the or.
    'publish.py:_block_ok:562:30:operand:0': 'publish.py:562',
    # Line 732 already returned for every value that is not an int or a float.
    'publish.py:_finite_number:732:7:operand:0': 'publish.py:732',
    'publish.py:_finite_number:734:7:operand:0': 'publish.py:732',
    # A missing feed is replaced by a list at line 86, which is killed.
    'publish.py:publish_view:127:31:operand:1': 'publish.py:86',
    'publish.py:publish_view:128:50:operand:1': 'publish.py:86',
    # The elif runs only when cut is 0, so prior is 0 and `not prior` is true.
    'publish.py:_level6:294:9:operand:1': 'publish.py:291',
    # A key that matches the pattern is shorter than TEXT_LIMIT and has no controls.
    'validate.py:_round_lists:589:11:operand:0': 'validate.py:589',
    # codecs.lookup ignores the trailing "~", so ascii and ascii~ decode alike.
    'read.py:read_line:351:59:constant:13': 'codec:ascii=ascii~',
    # 0x2029 is already in the explicit tuple, so the lowered bound changes nothing.
    'read.py:_bad_string:159:39:constant:0': 'read.py:159',
    # Every block key is a str, so a non-string is never a member.
    'publish.py:_merge_blocks:541:11:operand:0': 'strings:publish._BLOCK_KEYS',
    # exact_tree(blocks) already rejected a value that is not an exact tree.
    'publish.py:_merge_blocks:545:11:operand:0': 'publish.py:537',
    # The only ValueErrors json.loads can raise here carry a message, so
    # `exc.args` is never empty and dropping it cannot change the `and`.
    'read.py:read_line:372:27:operand:0': 'nonempty:read._pairs+read._reject_constant',
}
