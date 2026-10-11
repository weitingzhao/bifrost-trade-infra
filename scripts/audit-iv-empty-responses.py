#!/usr/bin/env python3
"""Read-only diagnostics for the approved 97 empty contract-days.

Runs in the Market Data image using its existing vendor client. No database
connection, ingest, queue, or feature writer. Private receipts contain metadata
and dates/counts, never vendor credentials or returned OHLC values.
"""
import argparse
import asyncio
import csv
import hashlib
import json
import math
import os
import re
import time
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path


def checked(path, digest):
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != digest:
        raise ValueError('reviewed diagnostic scope changed')
    return content


def load_scope(path, digest):
    rows = list(csv.DictReader(checked(path, digest).decode().splitlines()))
    if len(rows) != 97 or len({(r['option_ticker'], r['session']) for r in rows}) != 97:
        raise ValueError('diagnostic must contain exactly 97 unique contract-days')
    for r in rows:
        day, expiry = date.fromisoformat(r['session']), date.fromisoformat(r['expiry'])
        if (r['symbol'] not in ('SPY', 'NVDA', 'AAPL')
                or not date(2026, 8, 10) <= day <= date(2026, 8, 14)
                or not 50 <= (expiry-day).days <= 220 or r['status'] != 'no_bar_unknown'):
            raise ValueError('diagnostic exceeds approved target scope')
        if not re.fullmatch(r'O:'+r['symbol']+expiry.strftime('%y%m%d')+r'[CP][0-9]{8}',
                            r['option_ticker']):
            raise ValueError('ticker disagrees with symbol or expiry')
    return rows


def good(reply):
    return reply['http'] == 200 and reply.get('status') in ('OK', 'DELAYED', 'SUCCESS')


def classify(detail, catalogue, ticker, bars, day):
    if any(r['http'] in (401, 403) for r in (detail, catalogue, bars)):
        return 'permission_restricted'
    if not good(catalogue) or catalogue.get('truncated'):
        return 'reference_unprobed'
    if not good(bars) or bars.get('truncated'):
        return 'fetch_problem'
    membership = ticker in {r['ticker'] for r in catalogue['contracts']}
    if detail['http'] == 404 and not membership:
        if good(bars) and not bars.get('truncated') and not bars.get('days'):
            return 'not_listed_as_of_vendor'
        return 'reference_bar_conflict'
    if not good(detail) or not membership:
        return 'reference_conflict'
    if day in bars['days']:
        return 'retrievable_now'
    return 'listed_no_eligible_aggregate'


async def audit(rows, inputs, receipt):
    import httpx
    from bifrost_market_data.ingest._upsert import parse_option_ticker
    from bifrost_market_data.polygon.client import PolygonClient
    from bifrost_market_data.polygon.errors import PolygonAPIError
    report = {'status': 'running', 'attempts': 0, 'requests': [], 'controls': [], 'targets': [], 'alternatives': []}
    last = 0.
    contracts_fields = ('ticker', 'underlying_ticker', 'expiration_date', 'strike_price',
                        'contract_type', 'shares_per_contract', 'additional_underlyings')

    async with PolygonClient(os.environ.get('POLYGON_API_KEY') or os.environ.get('MASSIVE_API_KEY'),
                             tier='starter', max_retries=1) as client:
        async def get(kind, path, params):
            nonlocal last
            if report['attempts'] >= 320:
                raise RuntimeError('diagnostic HTTP cap reached')
            await asyncio.sleep(max(0., 1.-(time.monotonic()-last)))
            last = time.monotonic()
            report['attempts'] += 1
            try:
                status, data = await client._request_once(path, params)
            except PolygonAPIError as exc:
                status, data = exc.status_code, {'status': 'ERROR', 'error_type': type(exc).__name__}
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                status, data = None, {'status': 'ERROR', 'error_type': type(exc).__name__}
            answer = {'http': status, 'status': data.get('status'), 'request_id': data.get('request_id'),
                      'truncated': bool(data.get('next_url')), 'kind': kind}
            results = data.get('results')
            if kind in ('detail', 'catalogue', 'alternative'):
                records = results if isinstance(results, list) else [results] if isinstance(results, dict) else []
                answer['contracts'] = [{k:r[k] for k in contracts_fields if k in r} for r in records]
            else:
                from datetime import datetime
                from zoneinfo import ZoneInfo
                records = results if isinstance(results, list) else []
                answer['days'] = [datetime.fromtimestamp(r['t']/1000, ZoneInfo('America/New_York')).date().isoformat()
                                  for r in records if r.get('t') is not None]
                answer['record_count'] = len(records)
                answer['positive_close_count'] = sum(isinstance(r.get('c'), (int, float))
                    and math.isfinite(r['c']) and r['c'] > 0 for r in records)
            report['requests'].append({'path': path, 'params': params, 'answer': answer})
            receipt.write_text(json.dumps(report))
            return answer

        def agg_path(ticker, day):
            return f'/v2/aggs/ticker/{ticker}/range/1/day/{day}/{day}'

        for control in inputs['controls']:
            day, ticker = control['session'], control['ticker']
            detail = await get('detail', '/v3/reference/options/contracts/'+ticker, {'as_of': day})
            bars = await get('bars', agg_path(ticker, day), {'sort':'asc', 'limit':50000})
            report['controls'].append({**control, 'detail': detail, 'bars': bars})
            if not good(detail) or not good(bars) or day not in bars['days']:
                raise RuntimeError('positive historical control failed; stop diagnostic')

        groups = defaultdict(list)
        for row in rows:
            groups[row['symbol'], row['session'], row['expiry']].append(row)
        catalogues = {}
        for key, members in sorted(groups.items()):
            strikes = [parse_option_ticker(r['option_ticker'])['strike'] for r in members]
            params = {'underlying_ticker':key[0], 'as_of':key[1], 'expiration_date':key[2],
                      'strike_price.gte':min(strikes), 'strike_price.lte':max(strikes),
                      'expired':'false', 'sort':'ticker', 'order':'asc', 'limit':1000}
            catalogues[key] = await get('catalogue', '/v3/reference/options/contracts', params)
        for row in sorted(rows, key=lambda r:(r['symbol'] != 'SPY', r['symbol'], r['session'], r['option_ticker'])):
            day, ticker = row['session'], row['option_ticker']
            detail = await get('detail', '/v3/reference/options/contracts/'+ticker, {'as_of': day})
            bars = await get('bars', agg_path(ticker, day), {'sort':'asc', 'limit':50000})
            catalogue = catalogues[row['symbol'], day, row['expiry']]
            report['targets'].append({**row, 'classification':classify(detail, catalogue, ticker, bars, day),
                                      'detail':detail, 'catalogue':catalogue, 'bars':bars})
            receipt.write_text(json.dumps(report))

        # Reference metadata only: candidate replacement range stays within the
        # same three names and affected sessions, with the existing 50..220 cap.
        spots = {(r['symbol'],r['session']):r['spot'] for r in inputs['spots']}
        for symbol, session in sorted({(r['symbol'],r['session']) for r in rows}):
            spot = spots[symbol, session]
            if not isinstance(spot,(int,float)) or not math.isfinite(spot) or spot<=0:
                raise ValueError('historical spot missing')
            day = date.fromisoformat(session)
            params = {'underlying_ticker':symbol, 'as_of':session,
                      'expiration_date.gte':str(day+timedelta(days=50)),
                      'expiration_date.lte':str(day+timedelta(days=220)),
                      'strike_price.gte':round(spot*.9,4), 'strike_price.lte':round(spot*1.1,4),
                      'expired':'false','sort':'ticker','order':'asc','limit':1000}
            data = await get('alternative','/v3/reference/options/contracts',params)
            # No page walk beyond one page: incomplete metadata cannot become a
            # proposed request list. A bounded follow-up can inspect next pages.
            report['alternatives'].append({'symbol':symbol,'session':session,'spot':spot,'catalogue':data})
        report['status'] = 'read_only_diagnostic_complete'
        receipt.write_text(json.dumps(report))
    return report


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--manifest',type=Path,required=True);p.add_argument('--sha256',required=True)
    p.add_argument('--inputs',type=Path,required=True);p.add_argument('--inputs-sha256',required=True)
    p.add_argument('--receipt',type=Path,required=True)
    a=p.parse_args();rows=load_scope(a.manifest,a.sha256)
    inputs=json.loads(checked(a.inputs,a.inputs_sha256))
    report=asyncio.run(audit(rows,inputs,a.receipt));print(json.dumps(report))


if __name__=='__main__':
    main()
