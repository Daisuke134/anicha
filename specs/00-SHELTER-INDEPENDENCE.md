# Shelter Independence — 「Mac を売っても死なない」spec（順序の正本）

done="Franklin 本体が Nosana 上で常駐稼働し、Mac mini を停止しても lease 更新・署名・応答が続き、その第三者検証可能な証拠が揃って記事を publish できる"

方式: superpowers (Obra)。vcsdd は使わない（恒久ルール）。

## 検証済みの現状（2026-07-26 実測）

| 事実 | 証拠 |
|---|---|
| 自己資金で Nosana job を購入・応答確認済み | job `5dvaC3H2gB8Pfh…` IPFS ログ + HTTP/2 200（前セッション実測） |
| 現行 deploy は post して終了する一発屋 | `skills/self/shelter/nosana/deploy.mjs` — post→reconcile→return のみ。lease 監視・延長・再署名ループなし |
| 現行 job の中身は nginx:alpine（署名も agent もなし） | `deploy.mjs:24` `DEFAULT_IMAGE = "docker.io/library/nginx:alpine"` |
| `--confidential` は未実装・未使用 | `nosana/` 配下に "confidential" 出現ゼロ（rg 実測） |
| Franklin = `@blockrun/franklin`（Solana 自己資金 agent） | `life-manager-8i-cutover/README.md:48-53` |
| S9 の作業はディスク上に存在しない | anicha repo: commit 2件のみ・working tree clean・worktree なし。「走行中」は前会話内の申告で、実体なし |
| job definition は公開 IPFS に載る（in-job secrets 不可） | memory: nosana-shelter-hard-constraints |

## 残 TODO（この表が順序の正本。番号順に着手）

### A. 生存 — 「Mac を売っても死なない」3段（記事の本体）

| 順 | ID | 内容 | 状態 |
|---|---|---|---|
| 1 | S9 | 常駐化 — lease 全期間ループ + timeout 再読 + 毎サイクル blockhash 署名 | ✅ **完了 2026-07-26**。実測: live job `AnubczGS5FZmyqrEtv7AwJ2b7Ks1f7TTsYQ7HK2u3meo`（$0.012 自費）に steward attach、queued→running→success の全 lease を 14 cycles 常駐、`citizen-steward --verify --rpc` = **14/14 PASS（全署名有効 + 全 blockhash が実 slot と on-chain 一致）**。実装 main merge 済み（heartbeat.mjs / steward.mjs / bin/citizen-steward、77/77 tests、review PASS）。container 側の署名 loop は S12 で Franklin 本体ごと載せる |
| 2 | S8 | **sub-wallet 方式**で on-chain spend cap（設計転換 2026-07-26）。SPL Approve 委任は不可 — nosana-jobs `list.rs` の Anchor constraint が `user == payer 自身の ATA` を強制し delegate 経路を遮断（一次ソース: nosana-ci/nosana-programs list.rs + solana-program/token processor.rs L273-290、research agent 検証済み）。代替 = cap 分の NOS + 少額 SOL だけ入金した hot sub-wallet を作り、その鍵のみ cloud へ。cap 強制 = 残高そのもの（SOL 側も cap される分 delegate より強い）。@nosana/sdk `list(..., payer=subWallet)` が公式に payer 分離対応。refund も sub-wallet ATA に閉じる | ✅ **完了 2026-07-26**。E2E 実測: job `DzeUu64JRuFu8kNEnnwejUp5xkNjwPr1hm6fZRsk7zWW` を sub-wallet 支払いで post→16 cycles 常駐→success、escrow 残の refund も sub-wallet に返還確認（0.3077 NOS 残）。steward の slot/blockhash 分離 race も発見・修正（atomic *AndContext 化 + regression test）。review 指摘4件対応、main merge 済み。（旧記録: 実装 merge 待ち（branch `s8-subwallet`: sub-wallet.mjs + bin/citizen-subwallet + NOSANA_KEYPAIR_PATH override、88/88 tests）。実測済み: sub-wallet `71FfqFniYoMsWZb1qFeQDb1fk2xqvajzivpsnMb44gTf` を 0.35 NOS + 0.006 SOL で fund（sigs: 4YhApife… / 51A5Fnpx… / Q16AP7pD… / AaMhHDaz…）→ **job `DzeUu64JRuFu8kNEnnwejUp5xkNjwPr1hm6fZRsk7zWW` を sub-wallet 支払いで post 成功（API 実測 payer=71Ffq…）**、steward attach 済み。発見: CLI は escrow で `timeout 分の NOS`（0.3384）を要求 — estimateJobCost の見積($0.012)と別物、未使用分は返金。fee floor gate が SOL 0.004 を正しく拒否した実績も記録）| 
| 3 | S13 | `--confidential` job 実測 — ベンダー自身の秘密投入機構 | 🔄 **核心実証済み 2026-07-26**: confidential job `HsUW6Spd8Dzx5oXAfLB5ndQabfdVWPBGA4skAuJkWqQX` を live post（10分・owner 支払い）→ 公開 IPFS の CID `QmYBbVdW…` を ipfs.io + pinata の両 gateway で fetch = **stub のみ**（`ops:[]`, `logistics: api-listen`）— image/cmd/env は IPFS に載らない。`--confidential` は buildPostArgs 経由で実装済み（90/90 tests、branch `s13-confidential`）。✅ **完了 2026-07-26**。第2実証: poster CLI が死んだ状態では node は claim 後 `waiting-for-job-definition` で終了（state 2、timeStart 1785006025→timeEnd 1785006689 実測）= **confidential は poster プロセス常駐が必須**。未使用 escrow は返金確認（実験コスト ~0.028 NOS）。S12 への設計制約: confidential post は `--wait` 付きで長命プロセスとして spawn し、steward がその生存を管理する |
| 4 | S12 | Franklin 本体を Nosana へ | 🔄 **E2E 走行中 2026-07-26**。設計確定: sub-wallet が家賃 payer 兼 Franklin cloud 鍵（`.solana-session`=sub-wallet secret を confidential env で搬送、正本鍵は Mac を出ない）。branch `s12-franklin`: USDC leg + franklin-job.mjs + confidential-post.mjs（detached `--wait` poster）+ bin/citizen-franklin-up、98/98 tests。実測: USDC $0.025 fund（sig 2GkU2Ukj…）→ **confidential job `EGJ8SBtTUcbhSDRbEGTGVPsgfk56yty1DPhwraSPiMEE` post 成功**（poster pid 常駐、steward attach 済み）。発見: escrow 要求は duration 非依存で 0.3384 NOS 固定。exit proof = service URL が franklin の実出力を返す + sub-wallet USDC が実減 + IPFS stub |
| 5 | S14 | 独立の最終テスト — **Mac 全体は落とさない**（他の稼働系が載っているため）。Franklin/shelter 関連の Mac 側プロセスだけを停止し、Nosana 側が lease 更新・署名・応答を単独で続けることを実測。「Mac が消えても死なない」ことの証明であって、Mac を実際に消すことではない | S9+S8 の後 |

### B. 稼ぎ（$1.15/日 → 実 payout）

| 順 | ID | 内容 | 状態 |
|---|---|---|---|
| 6 | T2b | discovery catalog 登録 — 到達可能だが発見不可能 | 🔴 revenue $0 の残りの壁 |
| 7 | E7 | Gig を banked まで（実 payout rail） | 未着手 |
| 8 | F1 / T2 | トレードループ + 理由報告 / 稼ぎ面仕上げ | 🔄 |
| 9 | T2c | serve-mainnet.mjs 自己決済 — ETH $0.0165 で gas 不足、売れても決済不能 | 要 gas |
| 10 | S10 | 完成経路でブリッジ（片脚ブリッジは撃たない） | 🔄 |

### C. 記録・その他（A/B の後）

| ID | 内容 |
|---|---|
| A1 | 証拠パッケージ |
| T3b | 財務日報 |
| E5 | lane attribution |
| S11 | deployments 正規経路 |
| S4b | snapshot 自動化 |
| E6 | （未定義タスク — 前会話参照） |
| S5 | 再帰 self-host |
| E8 / E9 | 24h・7+14日 生存計測 |
| E1 | external — BLOCKED |
| F1-scale | $5,000 まで凍結 |

### 発見済みバグ（別タスク化済み）

| ID | 内容 | 証拠 |
|---|---|---|
| S15 | reconcileNosanaJobViaApi の `?payer=` は state-0 (queued) job を返さない → post 成功でも "post-unknown" 誤判定。RPC の List tx から fallback 照合を足す | 実事故 2026-07-26: job `Anubcz…` / tx `5ZSpxbWP…`。chip task_07588a71 |

## 記事のゲート

- 今証明済み: 「自分の金で家を借り、自分で更新し、家が応答し、中でコードが走った」— これだけでも公開前例なし（検索で見つからず）
- Dais が書きたい記事: 「Mac を売っても生きている」— S9 + S8（+S14 実測）が必須
- 判断: S9 → S8 を通してから書く。mock/fake の実績は一切書かない

## 参照

- 実装: `skills/self/shelter/nosana/`（deploy.mjs / job-definition.mjs / market.mjs / spend-gate.mjs / keypair.mjs / funding/acquire-nos.mjs）
- 制約 memory: nosana-shelter-hard-constraints（公開 IPFS・CLI extend/post 破損・no persistence）
- Franklin: `@blockrun/franklin`（npm）、参照 `~/Projects/life-manager-8i-cutover/README.md:48`
