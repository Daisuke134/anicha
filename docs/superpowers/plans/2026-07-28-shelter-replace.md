# SHELTER-REPLACE-1 Implementation Plan

> **工程ガード:** Superpowers の `using-git-worktrees`、`writing-plans`、
> `test-driven-development`、`verification-before-completion` に従う。

**Goal:** 稼働中の Franklin が6時間の lease 上限を迎える前に、自分の capped
wallet から後継 Nosana job を1件だけ発注し、第三者検証可能な service が生きたことを
確認してから引越し完了を記録する。

**Done:** 旧 job を含む同一 payer/market の active job が最大2件に制限され、後継の
`/`、`/statement.json`、`/heartbeats` が HTTP 200、最新 heartbeat の署名が有効になる。
失敗時は旧 runtime が継続し、retry は既存後継を再利用して二重発注しない。実 mainnet
job で list→claim→confidential delivery→readback を確認する。

**Architecture:** 現在の Nosana container 内の Python runtime が controller になる。
Mac/launchd/Modal の定期実行には依存しない。Nosana の payer-filtered job API を
durable ledger として使い、現 job より新しい active job があれば再利用する。なければ
残高床を検査して `list` を一度だけ送る。後継 definition は container 内の監査済み
Python source から再構築し、公開 IPFS には空の confidential stub だけを置く。

**Tech Stack:** Python 3.11、solders、PyNaCl、Nosana Jobs program、Nosana public API。

## 判断根拠

| 判断 | 一次ソース | 核心 |
|---|---|---|
| on-chain/API state を再起動後の台帳にする | [Nosana JobAccount](https://github.com/nosana-ci/nosana-programs/blob/10a64e45bc9b58bc2f696d407d13b37833767b7c/programs/nosana-jobs/src/state.rs) | `JobAccount` は payer、market、state、time_start、timeout を保持する |
| 後継発注額は残高床の前で止める | [Nosana list instruction](https://github.com/nosana-ci/nosana-programs/blob/10a64e45bc9b58bc2f696d407d13b37833767b7c/programs/nosana-jobs/src/instructions/list.rs) | `list` は payer の ATA から job deposit を vault へ移す |
| confidential definition は claim 後に node へ配送する | [Nosana CLI post action](https://github.com/nosana-ci/nosana-cli/blob/main/src/cli/job/post/action.ts) | CLI も post 後に `postJobDefinitionUntilSuccess` を実行する |
| extend と replacement は別の安全弁 | [既存 shelter roadmap](../../../ROADMAP.md) | successor は idempotent で、資金切れを生存と偽装してはならない |

## Task 1: 後継選択・二重発注防止をテストで固定

**Files:**
- Modify: `skills/self/shelter/python/test_nosana_bootstrap.py`
- Modify: `skills/self/shelter/python/nosana_bootstrap.py`

1. 現 job を除外し、同一 payer/market の active job を時系列で返す failing test を書く。
2. active job が3件以上なら fail closed、後継1件なら再利用する failing test を書く。
3. テストが意図した missing-symbol/behavior で失敗することを確認する。
4. 最小の選択関数を実装し、対象 Python tests を通す。

## Task 2: 公開 service と heartbeat の引越し検証をTDD実装

**Files:**
- Modify: `skills/self/shelter/python/test_nosana_bootstrap.py`
- Modify: `skills/self/shelter/python/nosana_bootstrap.py`

1. `/`、`/statement.json`、`/heartbeats` の全HTTP 200を要求する failing test を書く。
2. heartbeat の jobAddress、payer、署名を検証し、改ざんを拒否する failing test を書く。
3. 最小の `verify_successor_service` を実装する。
4. APIエラー・空heartbeat・署名不正で fail closed になることを確認する。

## Task 3: container 内から後継を一度だけ発注

**Files:**
- Modify: `skills/self/shelter/python/test_nosana_runtime.py`
- Modify: `skills/self/shelter/python/nosana_runtime.py`

1. lease ceiling 未到達では何もしない、ceiling 到達かつ margin 内でのみ動く policy test を書く。
2. 既存後継を再利用する、後継なしなら残高床後に1回 list する failing test を書く。
3. delivery/readback 失敗時に旧 runtime の heartbeat/statement serving が継続する test を書く。
4. source bundle から後継 definition を自己再構築する test を書く。
5. 最小の handover controller と renewal loop 接続を実装する。

## Task 4: definition 契約と全回帰を更新

**Files:**
- Modify: `skills/self/shelter/python/test_python_nosana_job.mjs`
- Modify: `skills/self/shelter/python/python-nosana-job.mjs`

1. replacement margin/ceiling/timeout のenv契約を failing test にする。
2. production default（6時間上限、上限前の引越し）を definition に追加する。
3. Python・Node shelter 全テストを実行する。
4. secret が command/receipt/public statement に出ないことを再確認する。

## Task 5: 実 mainnet handover と証拠

**Files:**
- Create: `specs/evidence/shelter-replace-<job>.json`
- Modify: `specs/00-SHELTER-INDEPENDENCE.md`

1. capped shelter wallet の残高、active job 数、Mac Franklin1 unloaded を事前readbackする。
2. production controller を force-once で起動し、実 list transaction を送る。
3. claim と confidential delivery を確認する。
4. 後継の3 endpoint HTTP 200と heartbeat 署名を独立検証する。
5. active job が最大2件、旧 job failure 時も後継が生きることを記録する。
6. 証拠JSONと shelter spec を更新する。

## Task 6: push・merge・Life Manager SSOT同期

**Files:**
- Modify: Life Manager consolidation spec

1. anicha を fetch→commit→push→PR→mergeする。
2. Life Manager SSOT の `SHELTER-REPLACE-1` を実証済みにし、次 cursor を
   `TASKMARKET-READBACK-1` に進める。
3. Life Manager 側も fetch→commit→push→PR→mergeする。
