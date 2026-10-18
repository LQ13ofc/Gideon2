TEST FIXTURES ONLY - fake GitHub server for S5/E1 (Connection Manager).
Never shipped, never installed, never published. No real service is contacted.

File: github_server.py  (python3 stdlib only, ThreadingHTTPServer, 127.0.0.1 only)
Run:  python3 tests/fixtures/connections/github_server.py --port 0
      Prints PORT=<n> on stdout once listening (0 = ephemeral).
      Port 0 is the default; an out-of-range port exits non-zero.
Logs: stderr, one line per request: "<METHOD> <path> <status>". No headers, bodies or
      token values are ever logged.
Tests: python3 scripts/test_connections_fixtures.py

OAuth device flow (contract docs/S5.md E1)
  POST /login/device/code              -> {device_code,user_code,verification_uri,expires_in:600,interval:1}
  POST /login/oauth/access_token       {device_code,grant_type}
       400 authorization_pending | 400 expired_token | 400 invalid_grant (unknown or already used)
       200 {access_token,refresh_token,expires_in:3600,scope:"a b",account}
       grant_type must be a non-empty string; form-encoded or JSON bodies accepted
  POST /login/oauth/refresh            {refresh_token} -> new token set; old refresh token is spent
                                       (400 invalid_grant when unknown, revoked or spent)
  POST /login/oauth/revoke             {token} -> 200 {revoked:true|false}; access or refresh token

API (Bearer auth; scope needed per route)
  GET   /api/repos                     repo:read   -> [{name,private,default_branch}]
  GET   /api/repos/{owner}/{name}      repo:read   -> {name,private,default_branch}
  POST  /api/repos/{repo}/issues       issues:write {title,body} -> 201 {number,title,url,state,public}
                                       Idempotency-Key: same key in same repo -> same issue, 201,
                                       header X-Idempotent-Replay: true
  PATCH /api/repos/{repo}/issues/{n}   issues:write {title?,body?,state?:open|closed}
  GET   /api/repos/{repo}/pulls/{n}    repo:read
  POST  /api/repos/{repo}/pulls/{n}/comments  pulls:write {body} -> 201 {id,body,url}
  GET   /api/repos/{repo}/actions      repo:read   -> [{id,name,status}]
  Error bodies: {"error": code}. 401 bad_credentials (missing, malformed, unknown, expired,
  revoked token); 403 insufficient_scope; 404 not_found; 405 method_not_allowed;
  429 rate_limited (+ Retry-After); 400 validation_failed / invalid_json / invalid_request.
  Every response carries X-Account: <current account name>.

Control endpoints (tests only)
  POST /__control/reset                    restore seed state, drop tokens, clear counters
  POST /__control/approve                  {device_code, scopes[]} user approves; denied scopes dropped
  POST /__control/expire_token             {} expires all access tokens; {access_token} or
                                           {device_code} expires that one (404 if unknown)
  POST /__control/rate_limit               {n, retry_after} next n /api requests get 429
  POST /__control/set_account              {name} (A-Z a-z 0-9 _ . -, max 39 chars)
  POST /__control/deny_scope               {scope} server refuses it: not granted, 403 on API
  GET  /__control/state                    issues, comments, requests, last_idempotency_keys,
                                           tokens {issued,revoked,active}, denied_scopes,
                                           rate_limit_remaining, device_codes_pending, account.
                                           Never contains token values.

Seed data
  demo/public-repo   public   default_branch main   issues #1 open, #2 open, #3 closed; pull #1 open; actions ci, lint
  demo/private-repo  private  default_branch main   issues #1 open, #2 open;            pull #1 open; actions ci, lint
  account demo-user

Limits
  Request bodies over 16 KiB -> 413 payload_too_large (nothing is applied).
  Chunked (Transfer-Encoding) requests -> 411.
  Unknown paths -> 404 for any method, with or without a token.
