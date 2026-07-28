# Shelter Independence — 「Mac を売っても死なない」spec（順序の正本）

done="Franklin 本体が Nosana 上で常駐稼働し、Mac mini を停止しても lease 更新・署名・応答が続き、その第三者検証可能な証拠が揃って記事を publish できる"

方式: superpowers (Obra)。vcsdd は使わない（恒久ルール）。

## 現在の判定

| 項目 | 現在の実測 |
|---|---|
| Mac Franklin1 | **unloaded**（`launchctl print` exit `113`）。Franklin2 は `state=running` のまま |
| cloud runtime | Nosana job `72zCpJEZLcM57DuPjCWthZBvKZyL3JH47zGwTidU2YKN`、service [`4ehZR…node.k8s.prd.nos.ci`](https://4ehZRtppzpMT4V2pKBbN9gKxBf67135c1iTndzCKuiZ3.node.k8s.prd.nos.ci)、3 public routes HTTP 200 |
| 生存証拠 | Python heartbeat **3/3署名検証PASS**。独立 JS verifier + Solana RPC でも **3/3 PASS**、全 blockhash が claimed slot と一致。lease は container 自身が `600→1800s` に延長 |
| 決算書 | 外部収入 `$0.00`、Nosana API の実単価から計算した snapshot runtime cost `$0.021870518`、verdict `funded` |
| 自動交代 | controller の実 mainnet handover 完了。旧 `5A6C…` state 1 → 後継 `72zC…` state 1 + public proof 検証 → 旧 state 2、終了後 active job は1件 |
| 証拠 | `specs/evidence/shelter-replace-72zCpJEZ.json`（旧 S21 証拠も履歴として維持） |
| current cursor | **TASKMARKET-READBACK-1**。自然な6時間 trigger の初回観測だけは W5 に分離し、実装順を止めない |

## 検証済みの履歴（以下は各時点のスナップショット）

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
| 4 | S12 | Franklin 本体を Nosana へ | 🔄 **E2E 走行中 2026-07-26**。設計確定: sub-wallet が家賃 payer 兼 Franklin cloud 鍵（`.solana-session`=sub-wallet secret を confidential env で搬送、正本鍵は Mac を出ない）。branch `s12-franklin`: USDC leg + franklin-job.mjs + confidential-post.mjs（detached `--wait` poster）+ bin/citizen-franklin-up、98/98 tests。実測: USDC $0.025 fund（sig 2GkU2Ukj…）→ **confidential job `EGJ8SBtTUcbhSDRbEGTGVPsgfk56yty1DPhwraSPiMEE` post 成功**（poster pid 常駐、steward attach 済み）。発見: escrow 要求は duration 非依存で 0.3384 NOS 固定。CLI は最低 0.005 SOL も要求。**確定した3知見**: ①moveCursor TTY crash は NODE_OPTIONS preload shim（shim/tty-shim.cjs）で根治 — poster が --wait で完走生存 ②confidential の定義搬送は poster→node の HTTP POST（postJobDefinitionUntilSuccess）で、poster 生存中なら成功（J4FW で実証: retrieved→validated→container started） ③**cmd は array 不可**: ["sh","-c",script] は node 側で ~3s 死、フラット文字列 cmd は稼働（A/B: probe job `6ceJBBkf…` の "probe up" が poster に stream された）。franklin def を string cmd に修正済み。✅ **本体達成 2026-07-26**: job `3DUJeSYDZdDFmZXr4u3hDbxuztWXysokEemQzn4fgUxt` で **Franklin が Nosana container 内で実走** — npm install→鍵展開→`franklin start` 実行→model 応答を生成→proof server が外部公開 URL `https://3qrxT3AofDWoUYcxh1ktV8NCz5g72JK6oNU5XftfMoA4.node.k8s.prd.nos.ci` で応答（実測 fetch、証拠: specs/evidence/s12-proof-3DUJeSYD.txt）。家賃は sub-wallet が on-chain 支払い、秘密は confidential p2p のみ、heartbeat 4/4 PASS。**S12b ✅ 解決 2026-07-26 — 「$5 デポジット床」は誤り（俺の前提ミス）**。実測: BlockRun は **Base の x402 で $0.003/call**（`POST https://blockrun.ai/api/v1/chat/completions` の 402 header = eip155:8453・USDC・amount 3000・payTo 0xe9030014…、デポジット床なし）。**founder wallet から実決済成功: HTTP 200 + gpt-5-mini の実出力、PAID tx `0x3abb9b69aab7…` success:true、USDC $4.995→$4.992**（`scripts/blockrun-buy.mjs`）。真因 = cloud Franklin が **Solana rail** で払おうとして verification に落ちていた。**S12c ✅ 達成 2026-07-26 — 完全自活が閉じた**: cap $1 の Base 専用 cloud 鍵 `0xd072CDDda8371D97834859E9c840F9B0F1e51a1d`（`scripts/base-subwallet.mjs` で生成、$0.50 seed、founder 鍵は Mac を出ない）を confidential env `BASE_KEY` で job `5gRY7ep9ntqq4qwDREAhwGYk3B5q9oTRn46EkS392Z5t` に搬送 → **container 内から自費で frontier 購入成功**: **tx `0xc785ae2336324228bf5fcfd19483e26e6749532429215ed935faee794574abe8`**、HTTP 200、モデル応答 = 「I am running inside a container rented by my own wallet, and I just paid for this sentence myself.」。cloud 鍵残高 $0.50→**$0.494** を on-chain 実測。公開 proof URL `https://3JosW9FaEVfguYzk5kXt8WNixantbTVhMFiw5PQK75Ge.node.k8s.prd.nos.ci`（証拠 `specs/evidence/s12c-frontier-selfpaid-5gRY7ep9.txt`）。x402=EIP-3009 なので cloud 鍵に **gas 不要**。潰したバグ: `npm i -g` は node の解決パスに乗らない → `/tmp/x402` にローカル install + 同 cwd 実行。**= 家（Nosana lease 自費）も餌（frontier 推論 自費）も、Mac 非依存で成立** |
| 5 | S14 | 独立の最終テスト — Mac 側プロセスだけ停止し Nosana 側の単独生存を実測 | ✅ **完了 2026-07-26**（S12 と同時実証）。手順: Franklin job `3DUJeSYD…` 稼働中に Mac 側の poster(pid 89603) と steward を kill（20:02:41Z、`poster-dead` 確認）→ その後も cloud service URL は **HTTP 200 で Franklin proof を返し続け**、lease は `2 success` で完走（monitor 実測）。= Mac が消えても Nosana 上の Franklin は生存。他の Mac 稼働系は無傷 |

| 6 | S16 | **注文する道具を agent に渡す**（家を「継承する」のをやめる） | ✅ **完了 2026-07-27**。それまでは人間が1軒目を post し agent は結果を受け取るだけ = 小遣いであって収入ではなかった。`skills/self/shelter/buy-house.mjs` を container に base64 一行で配送し、agent が自分の鍵で発注する。**live 実証: job `7cu6bmHzRnnEdetrzh3QYeWFuGjgKm8J9x5rufhxDdCs` の中から `{"ok":true,"rail":"modal","id":"sb-85okeYAh2O6PxtjD8s9Rrb","spentUsd":0.01}`** — 外部の誰も発注していない。cap は network 到達前に `planPurchase` が判定（$0.50/call）。2026-07-27 追加: 同じ verb に Nosana rail を実装（`buyHouseOnNosana` / `rentAnywhere`）— 呼ぶ側は「どちらの大家がどんな作法か」を知らなくてよい。これが blockrun-mcp への PR の中身になる |
| 7 | S17 | **決算書を agent 自身に公開させる**（生きている・自費で払った・稼ぎはゼロ、を第三者が検算できる形で） | ✅ **実装完了 2026-07-27**（`skills/self/shelter/statement.mjs`、9/9 + 全体 129/129 tests）。設計の核: **blacklist（秘密を消す）ではなく allowlist（宣言した field しか描画しない）**。理由 = Solana の署名と Solana の秘密鍵はどちらも base58 87-88字で、**形で見分けることが原理的に不可能**だから scrubber は当てにならない。自己決済は revenue に数えない（`from:"self"` を除外）ので、verdict は外部入金があるまで `funded` から動かない。`/` = 決算書、`/log` = 生ログ、`/heartbeats` = 検算用の生データ。container 側は各支出時に `/tmp/ledger.jsonl` へ1行書き、renewer が45秒ごとに最新 blockhash を自分の鍵で署名して heartbeat 行を足す | ✅ **live 実証完了 2026-07-27** — job `AzUFmVa5qeibfgXUpKW1szw7XXeK9x2S6JANkTnvhC3p`、公開 URL `https://2SRDLpUEKRXgpaAXMWs1KcVhmKGVofjgH4EBXcsqGsq4.node.k8s.prd.nos.ci`（証拠 `specs/evidence/s17-statement-AzUFmVa5.html` / `s17-heartbeats-AzUFmVa5.json`）。ページが実際に出したもの: 支出3件（飯 tx `0x186c1e56…` / 2軒目 `sb-axOzfUwsc0NwBE0Vo7kEqr` / **自己 lease 延長 tx `iJTfrgbF…`**）、収入 `$0.00 from outside`、heartbeat 12件。**第三者検証を自分で回した結果: 署名 12/12 有効・blockhash 12/12 が実 slot と chain 一致**。lease は 600→1200 秒に自己延長された（`jobs.get` = `state: RUNNING, timeout: 1200` 実測）。**発見して潰した表示バグ**: `toFixed(2)` が家賃 $0.008・思考 $0.003 を全部 `$0.00` に丸め、実 tx の隣に「何も起きていない」と表示していた。サブセントは4桁で出す（真のゼロだけは `$0.00` のまま — そこは見逃されては困る）。
| 8 | S22 / SHELTER-REPLACE-1 | **6時間の天井を「終了」ではなく「引越し」にする**。現在の Nosana container が capped shelter wallet で後継を1件だけ list、claim 後に confidential definition を配送し、`/`・`/statement.json`・`/heartbeats` と署名 heartbeat を検証して初めて handover 完了を記録する。payer/market/state/timeStart を public API の durable ledger とし、restart は既存後継を再利用。現 job + 後継の2件を上限にし、古い active peer や3件目は fail closed。 | ✅ **実装 + force-once live handover 完了**。最終 job `72zCpJEZ…`、list tx `jF6qqVd4…` finalized、confidential delivery HTTP 200、3 routes HTTP 200、heartbeat 3/3 は署名 + slot/blockhash とも独立検証PASS。旧 `5A6C…` は後継検証後 state 2、active=1。Python 63/63、Node shelter 197/197、CLI definition validation PASS。**証拠の限界:** wall-clock 21600秒 trigger 自体はまだ自然発火していない。待ちを6時間短縮するため同じ controller を force-once で呼んだ。自然発火の初回readbackは W5 |

### B. 稼ぎ（agent economy — diversified・全 rail real・dry ゼロ）

**資金の現在地（2026-07-26 実測）**: founder/economy wallet `0x810f6d61…` = **Base USDC $10.10** + ETH ~$0.03。他 colony wallet はほぼ $0（Franklin Solana ~$0.5相当、x402 0x6592=$0、PM 0x4c17=$0、HL 0xB9dd=$0、sol-trade 8Fpqd=$0）。**唯一の実資金 = Base の $10.10。**

**「dry runs じゃない」の保証基準（Dais 要件）**: rail が real か dry かは1点 — 実 tx 署名/実注文→**tx-hash/order-id を on-chain か API で検証→ landing 確認して ledger 記録**。LLM が「buy しろ」と言うだけ = 構造的 dry。payload に fake/dry/mock/phantom が出たら reject。

**trade rail 在庫の実査結果:**
| rail | real 執行? | 判定 |
|---|---|---|
| yield（Aave/Fluid/Beefy, Base）`execute-yield.mjs` | ✅ 実 tx + **phantom-guard**（landing 検証） | 採用・土台 |
| Polymarket `polymarket-trade/run.sh` | ✅ 実 CLOB（cap $2/$20 hard, adversary-reviewed, 実注文試行を実測） | 採用・エッジ（要修理） |
| Hummingbot（clone 実査） | ✅ 40+ venue 実注文の成熟 MM（DEX connector は KYC 不要） | 採用候補・24/7 MM |
| ✗ AutoHedge（`~/autohedge` 実査 633 LOC） | ❌ **LLM agent だけ、venue SDK/place_order 皆無** = 構造的 dry | 不採用 |
| ✗ Franklin-Trading / sol-trade | ❌ 半端（Dais 判定・未完成） | 不採用 |
| ✗ Hyperliquid `hl-trade` | — Dais が明示 OFF | 不採用 |

**diversification 方針**: ①yield（土台・Base 即・負けにくい）②PM（エッジ・修理）③Hummingbot DEX-MM（24/7 機械収入・導入）。単一 venue 非依存・全部 verify 可能・dry ゼロ。tokenized 株は Solana xStocks/Ostium が未配線 gap。

| 順 | ID | 内容 | 状態 |
|---|---|---|---|
| 6 | T2b | x402 discovery 登録 | ✅ **達成**。live `anicca-x402-discovery-production.up.railway.app/prompt-sanitizer`（payTo 0x6592, Base USDC $0.005, bazaar ext）、x402scan register 200 success（resource `3c716f96…`）。残 Task4 = self-buy で CDP Bazaar seeding（要 Base payer） |
| 7 | E7 | Gig を banked | 🔄 実案件 coconala `17943244`（取引中・v23 納品済・acceptance PASS）。**正式納品/検収 2026-08-14**＝banked 予定。外部人間+未来日付で今は強制不能、loop 維持中。本筋外 |
| 8 | **F1 yield** | Base 余剰を yield へ実 deploy | ✅ **達成・on-chain 検証済み 2026-07-26**。$5.10 USDC → **Fluid fUSDC 実着地（shares 4,536,729、5.36% APY、Base）**、$5 は compute reserve 温存。0x810f USDC $10.10→$5.00 を実測。loop の guard は "phantom" と誤検知したが on-chain の fUSDC share 残高で実着地を確認（＝self-report でなく chain で verify する規律が効いた）。**economy 初の real earning position・dry ゼロ**。※guard の phantom 誤検知は要修正（landing チェックが確定前に走る） |
| 9 | **F2 PM** | PM を実 fill に | 🟡 **実態判明 2026-07-26: 壊れてない。資金ゼロ + 勝ち position が満期待ち**。naked wallet `0x904B50d2e214Da947d83D6a2D32c4E3Ffc17Eb74` が「Fed 7月会合 no change」を **8 shares @0.6923 → 現在 0.8035 = 含み益 +$0.89(+16%)**、**決着 2026-07-29**（redeemable=false）。PM 系 wallet（0x904B50/0x4c17/0x99b3）は全て **USDC $0** — allowance エラーは現金ゼロで新規 quote を出そうとした結果。done = ①7/29 決着 → redeem で ~$6.4 現金化（自動、待ち）②現金が入ったら allowance 設定 → cadence 化 → 実 fill。**今すぐ強制できるのは②の allowance 準備のみ、①は満期日待ち** |
| 10 | **F3 Hummingbot** | KYC 不要 DEX connector で MM | ⏸ **保留＝capital-gated（実査 2026-07-26）**。KYC 不要 connector 実在（injective_v2/dexalot/derive/backpack/hyperliquid + gateway AMM）だが ①conda+Cython の重量インストール ②**$5 資本では MM が economically 成立しない**（両サイド在庫を置いて薄いスプレッドを取る商売、手数料/gas に食われる）。コード問題でなく資金問題。**着手条件 = 運用資本 $100+ に到達したら**。今やると「動くが稼がない」＝ dry の親戚 |
| 10b | **F4 x402 self-buy** | 自 endpoint に実決済1件 → CDP Bazaar seeding | ✅ **達成・on-chain 検証済み 2026-07-26**。`scripts/self-buy.mjs`（@x402/fetch + ExactEvmScheme、payer=0x810f≠payTo=0x6592 で INV-7 満たす）→ **HTTP 200 + 実サービス応答**（PII masked JSON）+ payment-response の `success:true, transaction 0x6878a285879527ccdf1a6d8f339c0708c55ec69f…`。**on-chain 実測: payer $5.00→$4.995 / payee $0→$0.005**。= **x402 経路が endpoint 公開→discovery 登録→実決済受領まで全部閉じた**。**掲載確認 2026-07-26**: x402scan = **登録が永続化されている**（再 register で同じ resource id `3c716f96…` + `success:true` + lastUpdated 更新を実測）。CDP Bazaar = settle 直後だが **全 14,257 件をページ走査して未掲載**（indexing 遅延と推定、要再確認）。x402scan の public read API path は非公開（複数候補が 404）。※INV-7 により self-payment は「稼ぎ」ではなく discovery seeding |
| 11 | T2c | serve-mainnet.mjs 自己決済 | 要 gas |
| 12 | S10 | bridge（片脚は撃たない） | Base $10.10 → 稼ぎ場（PM=Polygon 等）。frontier seed と x402 は Base 内完結 |

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

## D. Life Manager × Franklin — 製品の姿と最終形（Dais 2026-07-26 裁定）

### ★ 訂正（2026-07-27 深夜）: 前の「Life Manager には何も無い」は誤り — repo を取り違えていた ★

**間違いの経緯**: 調査を `/Users/anicca/Projects/life-manager` に対して走らせ、「wallet も payment も agent も無い」と結論した。**本物は `/Users/anicca/Projects/life-manager-main`**。見分け方は commit の新しさ（main は #1178 まで進んでいる／もう一方は 2026-07-11 で停止）。**一般法則: 同名の repo コピーが複数ある環境では、調査結果を採用する前に「一番新しい commit を持つのはどれか」を先に確定する。** colony の home 取り違えと完全に同型で、今回は**自分の調査 agent に間違った場所を指させた**ので俺の指示ミス。

### Life Manager の FINANCIAL organ — 実際に本番で生きているもの

正本: `life-manager-main/docs/handovers/2026-07-27-crypto-track-handoff.md` と同 repo の consolidation spec §9.8 / §9.11 / §10。

| 部品 | 実体 | 状態 |
|---|---|---|
| agent wallet | **`0x477EeE969ccfdc0e959F38cE8B83e372FC0262ad`（Base）** | 鍵は 0600 の protected store、repo/log/git に露出 0。**残高 0、seed 未定 — 勝手に入金経路を作るなと明記** |
| user への送金先 | **`0x6592EB8EF820aBC092e8C3474fb2042dffCCEDc7`** | 実 DB row、EIP-55 検証済み、`status: usable` |
| 収支台帳 | `lib/earnings-ledger.js` + `earnings-runtime.js` | append-only・minor-unit BigInt・損失月も盛らない月次 rollup・逐語 copy 生成。**45 tests merged、実収支行は 0 行** |
| 法的立ち位置 | spec §9.8 | **「AI が自分の wallet で稼ぐ。user 資産運用ではない」** |

**残っている2 leg（＝こちらの成果が刺さる場所）**
- **13c**: こちらの earn loop の実収益1件を `earnings-runtime` 経由で記帳 → 月次報告が実データで生成される（engine は完成、**行が無いだけ**）
- **13d-b**: agent wallet → `0x6592…EDc7` への on-chain 実 tx + §9.11 逐語 copy での TG 報告（前提: wallet に残高）

**破ると reject される約束**: ①台帳は向こうが正本、**こちら側に別台帳を立てない** ②user から取る個人情報は送金先1つだけ、追加要求禁止 ③損失月も正直に ④tx は basescan link 付き ⑤spend-cap = 残高、超過はコードで不能に ⑥変更は PR + fresh adversary review

### Life Manager は何なのか（3択への回答）

| 案 | 判定 |
|---|---|
| Franklin 群の管理者 | ❌ 違う。管理対象としての Franklin 群は存在しないし、必要でもない |
| **自分の wallet を持ち、自分の道具・計算・住処を払い、自分のために稼ぐ agent** | ✅ **これ**。spec §9.8 が明示（「AI が自分の wallet で稼ぐ。user 資産運用ではない」）。送金先が既に取ってあるのは、稼いだ分を人間に**送る**ため |
| Franklin そのもの | ❌ 違う。Franklin は道具（`@blockrun/franklin`）であって主体ではない |

**したがって shelter の仕事は「別製品」ではなく「Life Manager の agent が Mac の外で生き、自分の計算を自分で払うための臓器」。** merge とは、こちらが**on-chain の事実を作り**、向こうの台帳が**それを記録し**、向こうの copy bank が**それを報告する**、という3段の接続のこと。

## E. 実測で得た全 gotcha（再発見コスト回避・2026-07-26）

再検索すれば分かることでも、この一覧が無いと毎回同じ壁に当たる。全て実測。

### Nosana / shelter
| 事実 | 詳細 |
|---|---|
| escrow は duration 非依存 | 10分でも15分でも **0.3384 NOS 固定**で押さえられる。未使用分は終了時に返る |
| CLI は最低 0.005 SOL を要求 | 残高がそれ未満だと post 自体を拒否（gate とは別の CLI 側チェック） |
| `--confidential` は poster 常駐必須 | 定義は poster→node の HTTP POST（`postJobDefinitionUntilSuccess`）で渡る。poster が死ぬと node は `waiting-for-job-definition` で終了 |
| 公開 IPFS には stub のみ | confidential 時 CID の中身は `ops:[]` + `logistics: api-listen`。両 gateway で実測 |
| container の `cmd` は **flat string 必須** | `["sh","-c",script]` の array 形は node 側で ~3s 死ぬ。A/B 実証済み |
| CLI は piped stdout で crash | `process.stdout.moveCursor` を呼ぶ。`NODE_OPTIONS --require shim/tty-shim.cjs` で no-op 化して根治 |
| `nosana job extend` CLI は壊れている | `extend/action.js:23` が undefined の `config.network.includes()` を呼ぶ。**SDK 直呼び `jobs.extend()` は動く**（renew.mjs） |
| `?payer=` API は queued job を隠す | state 0 の job が返らない。reconcile は RPC の List tx から補完が要る（S15 バグとして chip 化済み） |
| service URL は決定的 hash | `getExposeIdHash(jobAddress, opIndex, port)` + `.node.k8s.prd.nos.ci` で導出可 |
| SPL Approve 委任は使えない | nosana-jobs `list.rs` が支払い元を poster 自身の ATA に固定。cap は「残高そのもの」で担保するしかない |

### x402 / 支払い
| 事実 | 詳細 |
|---|---|
| BlockRun に**デポジット床は無い** | Base の x402 で **$0.003/call**（402 header: eip155:8453 / USDC / amount 3000 / payTo 0xe9030014…）。「$5 床」は誤情報だった |
| cloud 鍵に **gas 不要** | x402 は EIP-3009（署名だけで送金委任、手数料は受取側負担）。対象トークンだけ持たせればよい |
| 402 の中身は **header** にある | body は `{}`。`PAYMENT-REQUIRED` を base64 decode すると payTo/accepts/extensions が出る |
| client config の形 | `wrapFetchWithPaymentFromConfig(fetch, {schemes:[{network, client: new ExactEvmScheme(account)}]})`。scheme を裸で渡すと落ちる |

### x402 discovery 登録（x402scan）
| 事実 | 詳細 |
|---|---|
| register は `POST https://www.x402scan.com/api/x402/registry/register` body `{url}` | SIWX 認証必須 |
| **署名者 = payTo である必要は無い** | submitter-auth であって所有証明ではない（throwaway EVM 鍵で通過を実証） |
| 署名する文字列 | EIP-4361/SIWE plaintext。**chainId は数値 `8453`**（header payload 側は CAIP 文字列 `eip155:8453`） |
| 提出方法 | 同じ body + header `SIGN-IN-WITH-X: base64(JSON payload)`。payload = challenge の全 info + address + signature |
| 時間制約 | issuedAt から 5分・nonce は single-use。取得〜提出を1スクリプトで完結させる |
| `no_discovery` の真因 | resource は probe されない。**`GET {origin}/openapi.json`** を取りに来て OpenAPI doc の `x-payment-info` を読む（@agentcash/discovery 1.7.5） |
| openapi.json の必須形 | `openapi`/`info.title`/`info.version`/`paths` + 該当 path の `x-payment-info.price = {mode:"fixed", amount, currency}` |
| CDP Bazaar は settlement-driven | 初回決済後に index される。read API は `GET https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources`（無認証） |

### 2軒目（Modal gateway）の硬い制約 — 大家は互換ではない（2026-07-27 実測）

**`Only managed image python:3.11 is currently available.`** node:20 も nginx:alpine も 400 で拒否。つまり:

| | 1軒目 Nosana | 2軒目 Modal gateway |
|---|---|---|
| image | 任意のコンテナ | **python:3.11 のみ** |
| 公開 URL | あり（`getExposeIdHash` で導出） | gateway-native は無し。workload 自身が Cloudflare Quick Tunnel を起動すれば **一時URL** は出せる |
| Franklin(npm) が動くか | ✅ | ❌ **node が無い** |

**冗長化の正確な主張:** Node 版 Franklin の同一バイナリは2軒目で動かない。一方、Python 版の最小生存機能（x402 決済、署名 heartbeat、allowlist 決算書）は2軒目で実証済みなので、**同じagent実装の冗長化ではなく、同じ生存契約の異種runtime冗長化**が成立する。x402 の Python SDK v2 には EVM の exact scheme が同梱されていないため、EIP-3009 を手で組む。

### 金を動かす loop で踏んだ2つ（live でしか出なかった・2026-07-27）

どちらも**テストは緑のまま**で、実行して初めて出た。

**① cap は「入れる量」の上限であって「持っている量」の上限ではない。** funding gate が全 asset の cap を無条件に検査していたため、sub-wallet の SOL が cap 超過（0.026 > 0.005）なだけで **NOS の補給が丸ごと拒否**された。しかもその SOL は誰かが送ったのではなく **Nosana の escrow 返金で戻ってきたもの**。NOS を拒否しても SOL のエクスポージャは1 lamport も減らない。→ cap は**補給する asset だけ**に適用し、既存の超過は warning として表に出す（黙って他を止めない）。

**② 金が動いた後に結果の形が読めないなら、「失敗」と報告してはいけない。** `fundSubWallet` は `sent` を返し、`executeRefill` は `ok` を読んでいた。**tx `aYGEcC5k…` が 0.473 NOS を実際に送った直後に loop は `top-up failed: unknown` と報告**した。これを読んだ retry loop は二重送金する。→ rail 側は `ok` を明示、呼び出し側は両方を読み、**どちらも無い場合は failure ではなく `indeterminate`**（「送金は成立した可能性がある。チェーンを見てから再送しろ」）。

**一般法則: 金を動かす関数の成功フィールドは推測させてはいけない。推測が外れた時の既定値が「失敗」だと、その既定値が二重支払いを生む。**

### 運用一般

**★ 時間の天井は金の床の代わりにならない（2026-07-27 実測）★**: renewer は「1回 +600秒・1 lease は 6時間まで」という**時間**の制限だけを持っていた。結果 job `AzUFmVa5` は 600→**19800秒**（5.5時間）まで自分で延長し続け、shelter wallet を **0.894 → 0.027 NOS** まで焼いた（≈$0.23）。残 0.027 NOS では次の10分 lease（0.0302 NOS）すら買えない = **agent は自分の家賃で自分をホームレスにした**。SOL はむしろ増えた（0.0143→0.0235、escrow 返金）ので「SOL があるから大丈夫」は誤読。**一般法則: 自動的に金を使う loop には、上限（1回いくらまで）と別に床（残高がここを割ったら止める）を必ず置く。上限だけでは残高ゼロに向かって正常動作し続ける。** 反例として床が要らないのは、支出が1回きりで再入場しない loop だけ。


**★ colony home を取り違えると「資金が消えた」ように見える（2026-07-27 実測）★**: `citizen-franklin-up` を `ANICCA_HOME=/Users/anicca/.anicca-founder` で起動したら、`ensureSubWallet` が**新品の空 sub-wallet `Hxmoj5tT…` を生成**し `spend gate: REFUSED — have 0 NOS` で停止した。資金のある sub-wallet `71Ffq…` の正しい home は **`/Users/anicca/.blockrun`**。鍵は1つも失われていない（`ensureSubWallet` は既存ファイルがあれば必ず読むだけで、上書きは構造的に不可能 — sub-wallet.mjs:142-154）。**復旧手順**: 稼働中の poster の env を見る（`ps eww -p <pid> | grep ANICCA_HOME`）。これが正解の home を持っている唯一の生き証人。**一般法則: 残高ゼロを機能の欠陥と診断する前に、どの identity で走らせたかを確認する**（PM の `allowance not enough` と完全に同型の誤診）。

| 事実 | 詳細 |
|---|---|
| `npm i -g` は node の解決パスに乗らない | container 内では専用ディレクトリにローカル install し、その cwd で実行する |
| Railway の env は `--service` 必須 | 付けないと silent に無視され、app が起動時 env 欠落で死ぬ |
| Railway `npm ci` は lock 不整合で落ちる | `nixpacks.toml` で install phase を `npm install` に上書き |
| Node に `globalThis.crypto` が無い環境がある | CDP SDK の Ed25519 JWT が `crypto is not defined` で死ぬ。`webcrypto` を global に注入 |
| loop の自己申告は信用しない | yield loop が「phantom」と誤検知したが、on-chain の share 残高では**実着地していた**。判定は必ず chain 側で |

## ★ 優先順位（Dais 裁定 2026-07-27 深夜・更新）★

**待つ仕事と、待たない仕事を分ける。** 外の世界に依存するもの（買い手が現れる・Dais が入金を決める・PM が 7/29 に決着する・上流が PR を見る）は**待つしかない = 着手順から外す**。待っている間、外部依存ゼロの工学だけを番号順に潰す。「待ちながら何もしない」は禁止。

**旧裁定との差分**: 前の表は「1 稼ぎ loop を real にする」を最優先にしていた。これは**着手できない仕事を1番に置いていた**ので誤り — 稼ぎが real になる条件は「見知らぬ他人が払う」であって、こちらの作業量では動かない。導線（PR・商品）は作り終えているので、あとは待ちに回す。

### 待たない（今やる。全部こちらだけで閉じる）

**現在地**: 支出側・異種runtime冗長化・Mac-off・earning rail health contract・Nosana shelter handoverまで閉じた。次は **TASKMARKET-READBACK-1: 実 work loop の結果を Life Manager 台帳へ exactly-once で戻す**。外部payerの出現だけに依存する13c-SELLは待ちへ分離する。

| 順 | ID | やること | 状態 / なぜこの順か |
|---|---|---|---|
| ~~1~~ | S18 | renewer に金の床 | ✅ 完了。実残高 0.0267 NOS で `renew=false` を実測 |
| ~~2~~ | S19 | 収入 → bridge → swap → sub-wallet top-up | ✅ 完了。live で 0.0267→0.5 NOS、tx `aYGEcC5k…` finalized |
| ~~1~~ | **S20b** | **2軒目で生き延びる（Python 版の最小生存機能）** | ✅ 完了。x402、Python heartbeat、公開allowlist決算書を同じ `python:3.11` rail で実証。Node版Franklinではなく生存契約の異種runtime実装 |
| ~~1~~ | **S21** | bootstrap を Modal へ（Mac の関与を資金だけにする） | ✅ **完了**。Python が hand-built list instruction、confidential delivery、restart recovery、自己renewを実行。Mac Franklin1 unloaded 後も heartbeat/決算書が継続 |
| ~~1~~ | **EARN-HC-1** | earning rail health contract | ✅ **完了**。8/8 instrumented、NOT-INSTRUMENTED 0。PM/x402/WORK/CAPITALは4/4 operational、inactive railはfrozen/not-liveへ固定 |
| ~~1~~ | **S22 / SHELTER-REPLACE-1** | 6時間 ceiling 前に successor を list→confidential deliver→public proof verify | ✅ 実装 + force-once mainnet handover完了。wall-clock自然発火だけW5で観測待ち |
| **1** | **TASKMARKET-READBACK-1** | 実 work loop の verified result を Life Manager earnings ledger へ exactly-once 記帳 | **current cursor**。既存 loop の実結果を readback して月次報告へ接続する |
| 待ち | **13c-SELL / 13c-WORK** | colony外buyer/jobから累計 `$1` のverified着金 | external payer + finalized receipt + provenance が必要。self-payは0、現在の外部収益は `$0.00` |
| 3 | D群 | Life Manager 接続（custody / dashboard / cap UI / 法務） | agent economyをコード統合せず、wallet/ledger/health contractの3契約でLife Managerから管理する |
| 4 | F群 | 記事 EN 更新 → JP | 数字待ちだが、**仕組みと検証手順は今書ける**。冗長化の記述は S20b の結果で書き換えが要る（現状の主張は実測より強い） |

### 1〜4 の「どうやるか」— 調査完了（2026-07-27、全部一次ソース読み）

#### S20b: 2軒目で生き延びる

| 要件 | 状態 | どうやるか |
|---|---|---|
| **x402 決済** | ✅ **完了・実測済み** | `skills/self/shelter/python/x402_pay.py`。`eth_account` + `requests` のみ。**実 tx `0x315fe61b…`、Base block 49161947、receipt status 0x1**。13 tests。黙って失敗する定数3つ: header は v2 で `PAYMENT-SIGNATURE`（v1 の `X-PAYMENT` を送ると **402 が返るだけで原因が見えない**）／amount は base unit なので**変換したら署名は有効なまま違う額を払う**／署名の `0x` は `HexBytes.hex()` が付けない |
| heartbeat 署名 | ✅ **完了・実測済み** | `skills/self/shelter/python/heartbeat.py` + `modal-heartbeat.mjs`。Modal sandbox `sb-0l4DnecMvMpXm4OzLLcFTn` 内だけで一時 Ed25519 鍵を生成し、同一公開鍵で約5.3秒間隔の2周期を署名（slot `435525136`→`435525148`）。既存 JS verifier + `citizen-steward --verify --rpc` が **2/2 PASS、blockhash も実 slot と一致**。証拠: `specs/evidence/s20b-python-heartbeat-sb-0l4DnecMvMpXm4OzLLcFTn.jsonl`。成功サイクルの実費は create $0.012 + exec $0.003 = **$0.015**。API の1引数2000文字制限を live で発見し、公開ソースを複数引数へ分割する回帰テストを追加。長期 wallet secret は sandbox に渡していない |
| 決算書 serve | ✅ **完了・実測済み** | `statement.py` + `modal-statement.mjs`。Modal `sb-34xzazUQKuoGKBFWeh1PQ6` が一時URLの `/`・`/statement.json`・`/heartbeats` を全て **HTTP 200** でserve。再帰allowlist、外部収入 `$0.00`、runtime `$0.015`、`funded` を明記。Base USDC `1.766`、SOL `0.026094157`、NOS `0.5`、PM 2 positions / marked value `$7.9951` / cashPnl `$1.1166` / redeemable `0` は独立再読込と差分ゼロ。heartbeat は既存JS verifier + RPCで **2/2 PASS**。証拠: `specs/evidence/s20b-python-statement-sb-34xzazUQKuoGKBFWeh1PQ6*`。Quick Tunnel は開発用・一時的・SLA無し、lease は5分。liveで DNS公開遅延とx402 exec後決済を踏み、両方を有限リトライの回帰テストへ固定。S20b全デバッグ+証明費は `$0.075` |

#### S21: Mac を外す — **✅ LIVE COMPLETE**

| 検証 | 結果 |
|---|---|
| paid bootstrap | Modal `sb-wfum2N1044meGAswyc3zSC`、create + 3 exec 全HTTP 200。list tx `wHBwJ8…Qq4ZB` finalized |
| confidential | 公開CID `QmYBbVd…DMBph` は `ops:[]` のstubだけ。秘密定義はclaimed nodeへsealed ciphertext経由で配送、HTTP 200 |
| cloud service | job `DdUqQh8…WPS4`、[`service URL`](https://3r9A3tsCCbuMCXxbKLbKGJVfpFofga6q69Tt4vUYZKMY.node.k8s.prd.nos.ci) の `/`・`/statement.json`・`/heartbeats` がHTTP 200 |
| heartbeat | 自然間隔4周期を独立 verifier で **4/4 PASS**。全行が同じjob/payerへbind |
| 決算書 | `runtimeCostUsd` は固定値ではなくNosana APIの `usdRewardPerHour × timeout / 3600`。`2400s × $0.043345153/h = $0.0288967687`、公開値と一致 |
| self-renew | container自身が `600→2400s`。extend tx `4Me9s…QLHWv` / `3Y549…NLKy` / `4enWU…D2x4` は全finalized。`0.34 NOS` move-out reserve + `0.005 SOL` fee floorで停止する |
| Mac-off | Franklin1 launchd はunloaded（exit 113）。Franklin2はrunning。Mac側writerなしでもcloud heartbeat/statement継続 |
| exactly once | 2回目 Modal `sb-52EMSJtDW5vQI8fE11NUD3` は同じjobをrecoverし、`listSignature=null`、service reconcile HTTP 200 |

**liveで棄却した前提**:

| 前提 | 実測と修正 |
|---|---|
| Modalは2 execで足りる | claimが同期execの約60秒より長い。prepare → background bootstrap → collect の**3 exec**へ変更 |
| indexer障害は「jobなし」と同じ | 一時障害でduplicate listを1件作った。探索不能時は**fail closed**に変更し、emptyを証明できた時だけlist |
| 同時bootstrapはAPI照合だけで防げる | 2 processが同じempty snapshotを見るraceをliveで検出。shared persistent stateのatomic writer leaseを追加 |
| 決算書のruntime costはModal固定 `$0.015` でよい | Nosana上では誤り。live job APIから動的算出し、旧jobを停止・返金後に修正版を再配置 |

Python から Nosana に job を post する経路を一次ソースで確認した。

| 部品 | 実態 | 出典 |
|---|---|---|
| Python SDK | **存在しない**。`nosana-ci/nosana-python-sdk` は **size 0 の空 repo**（README 0 バイト）。PyPI にも無し | `gh api repos/nosana-ci/nosana-python-sdk` |
| `anchorpy` で IDL を読む | **不可**。`anchorpy-core` の IDL parser は 2023-12 で止まっており、Anchor 0.30.0(2024-04) の IDL 仕様変更に未追従。Nosana は **Anchor 1.0.2** でビルド。該当 issue が未解決で複数（#147/#163/#167/#149） | `Anchor.toml`、anchorpy の open issues |
| 迂回策 | **命令を手で組む**。Anchor の discriminator は仕様不変で `sha256("global:list")[:8]`。program ID `nosJhNRqr2bc9g1nfGDcXXTXvYUmxD4cVwy2pMWhrYM`、`list(ipfs_job:[u8;32], timeout:i64)`、必要 account 一覧と PDA 導出は公開ソースに全部ある。`solders`/`solana-py` は現役 | `nosana-programs/programs/nosana-jobs/src/instructions/list.rs`、Anchor `lang/syn/src/codegen/program/common.rs:11-17` |
| REST の write 経路 | **使えない**。`POST /jobs/list` は存在するが SDK が送信前に `API key is required` で throw。Nosana の有償 Deployments 向け | `@nosana/sdk` `dist/client/index.js:15-16` |
| IPFS pin 先 | 新規pinは不要。Nosana公式confidential stubの既存immutable CIDをgateway body + CID digestの両方で検証して再利用 | live CID `QmYBbVdWFgfoTEdPT7mnaXJz6zQzfKb1Pts4A5B9kDMBph` |
| confidential 配送 | poster が node の `/job/{id}/job-definition` に**5秒ごとに再送**。認証は「IPFS hash の生バイトを ed25519 署名して `<msg>:<base58(sig)>:<epoch_ms>`」 | `nosana-cli` `postJobDefinitionUntilSuccess`、`dist/services/authorization.js:10-46` |

**非自明な唯一の難所 = PDA 導出と命令の手詰め。** それ以外は `requests` と ed25519 署名だけ。

**★ 実装結果: Pinata資格情報を持たない ★** confidential public stubは内容が固定で秘密を含まないため、既存immutable CIDをdigestとbodyで毎回検証して使う。Nosana同梱JWTもDaisの個人credentialも不要。

#### D群: Life Manager — **コードmergeではなく3契約で接続**
接続点は ①wallet/cap、②earnings ledger、③rail health + daily/weekly report。agent economyのexecutorは隣接repoに保ち、Life Managerは人間向けsubscription、資金投入、権限、報告、法務境界を持つ。S21とEARN-HC-1により、管理対象のcloud citizenと機械判定可能なrail状態が実在する。

#### F群: 記事 — 冗長化の記述が実測より強い

07-27 EN 版に書き換えが要る箇所が **9行**。特に自分で制約を書いてしまっている1行:
> "One HTTP POST with a Base key, and the response is a running **Python 3.11** box."

そして実測と矛盾する1行:
> "That asymmetry is why an agent that can use both rails is stronger than one that has mastered either."

**Node の agent は2軒目で動かない**（`Only managed image python:3.11 is currently available.`）。ただし Python 版の x402 + heartbeat + 決算書は2軒目で実証済み。「同じものが両方で動く」ではなく、**同じ生存契約を異種runtimeで満たす**と書けば真になる。Quick Tunnel は恒久公開基盤ではないことも併記する。

### 稼ぎ loop の実稼働状況（2026-07-27 実測・ログ全読み）

**PM は dry ではない。実注文・実約定・実 redeem が回っている。**

| 観測 | 証拠（`~/.hermes/state/pm-live-trade.log`） |
|---|---|
| 実 redeem 2回 | `pUSD after: 7.086184 (recovered: 6.0)` / `pUSD after: 7.572182 (recovered: 6.994283)` |
| 実発注 | `YES 7@0.53 ok=True status=live id=0x66dfd152c4` ほか計7件 |
| 資金の循環 | 1.086 → 展開 → 7.086 → 展開 → 0.578 → 7.572 |
| 現在 | deposit wallet `0x904B50d2…` に **7.572 pUSD** |

**★ ただし「いくら儲かったか」はこのログからは分離できない ★** `recovered` は元本の戻りと利鞘が混ざった数字で、各サイクルの展開額が記録されていない。**これが 13c（Life Manager の earnings-ledger に記帳）が要る理由そのもの。** 台帳が無いと、実際に金が動いていても収益を主張できない。

**earn-watch の redeem 脚は死んでいた（別経路が生きていたので損害はゼロ）**: `earn-watch.sh:23` が裸の `timeout` を呼び、launchd の PATH に無いので `REDEEMABLE=2 -> redeeming` の直後に落ちていた。spec は「このバグは潰した」と書いていたが、**実際に直っていたのは `reinvest.sh` だけで `earn-watch.sh` は直っていなかった**。絶対パスに修正済み（`bash -n` 通過、launchd 相当 PATH で実行して exit 0）。**redeem 自体は pm-live-trade 側が実行していたので取り残された金は無い** — 「片方が壊れていたが冗長経路が拾っていた」ケース。**一般法則: 同じバグを複数ファイルで踏んでいる時、1つ直して「潰した」と書くと残りが見えなくなる。修正は grep で全件確認してから完了と書く。**

| loop | 状態 |
|---|---|
| `pm-live-trade` | ✅ 実稼働（1時間ごと・実約定・実 redeem） |
| `reinvest` | ✅ 稼働（`yield_hold` を正常出力） |
| `earn-watch` | 🔧 redeem 脚を修正（冗長経路が生きていたため実害なし） |
| Hummingbot MM | ⏸ 未着手（運用資本 $100+ 待ち） |
| x402 売り | 🔴 出品済み・**外部購入 0 件** |

### 自活に必要な額（実測単価から算出）

| 項目 | 実測単価 | 24/7 の月額 |
|---|---|---|
| 住処（Nosana 最安 GPU market） | **$0.04796/hr** | **$34.5** |
| 2軒目 standby（Modal, CPU 300s） | $0.01/300s | 常時なら $86（**失敗時のみ使う前提**なので実質 ~$1） |
| 思考（frontier, x402） | **$0.003/call** | 20 call/hr なら **$43** |
| Solana 手数料 | ~0.000005 SOL/tx | 実質 0（ただし 0.005 SOL の床は常時保持） |
| Base gas | **0**（EIP-3009 は署名のみ、受取側が払う） | 0 |
| **合計** | | **月 $78 前後**（住処 $35 + 思考 $43） |

**節約版**: 思考を 5 call/hr に落とせば月 $46。**最小生存（住処だけ・思考は必要時）なら月 $35。**

**現在の収入**: 外部から **$0.00**。PM の利鞘は実在するが台帳が無く分離できない。yield は月 $0.02。**したがって自活まで足りないのは月 $35〜78。**

### 実装の回し方（Dais 裁定 2026-07-27）

**実装は executor subagent に出す。orchestrator は spec 管理と E2E 検証に専念する。** 理由は context — 実装の生ツール出力を orchestrator の窓に流し込むと、順序の正本（この spec）を保つ余力が先に尽きる。手順は flow A hybrid: spec/plan を書く → `.worktrees/<id>/` を切る → executor が TDD で実装 → orchestrator が実チェーン/実コマンドで検証 → merge → worktree 削除。**executor には `--live` を絶対に渡させない**（実際に金が動く操作は orchestrator が自分で撃って自分で検証する）。

### 財布の階層（S19 で踏んだ穴・2026-07-27）

**instance には財布が2段ある。混同すると「補給したのに家が借りられない」が起きる。**

| 段 | 誰 | 実測（2026-07-27 深夜） | 役割 |
|---|---|---|---|
| treasury | owner `F5SYUC4f5QULbEgSYb1DFCBfi74AnWE3ZaXAhqXwhZ5T` | **0.607 NOS** | 資金の受け皿。`resolveSolanaSecret` が返すのはこっち |
| shelter | sub-wallet `71FfqFniYoMsWZb1qFeQDb1fk2xqvajzivpsnMb44gTf`（`$ANICCA_HOME/.automaton/nosana_subwallet_key.json`） | **0.670368 NOS / 0.013662961 SOL**（SHELTER-REPLACE-1 snapshot、top-up cap 0.75 NOS） | **家賃を実際に払う**。cap = 残高。cloud へ出る鍵はこれだけ |

S19 の初回実装は treasury だけを見て「補給が要る」と判断していた。だが treasury は既に潤沢で、飢えているのは shelter の方。**橋は正しく渡るが、家賃を払う財布の1つ手前で止まる。** 補給は3脚（bridge → swap → **top-up**）で、最後の `fundSubWallet` が無いと何も解決しない。各脚は前の脚が成功した時だけ走る（届いていない金は動かせない）。

**一般法則: 「残高が足りない」を直す前に、足りないのが*どの段*かを確定する。** 上の段を満たしても下の段は飢えたまま。→ [[colony-wallets-where-the-money-actually-is]] と同型（あちらは instance 違い、こちらは同一 instance 内の段違い）。

### 待つ（着手順に入れない。条件が満たされた瞬間だけ動く）

| ID | 待っているもの | 満たされたら何が起きる |
|---|---|---|
| W1 | **外部の買い手が1人払う** | `Earned $0.00 from outside` が初めて動く。これだけが「funded」→「earning」を反転させる |
| W2 | Dais の入金判断 | S18 が入ってから。目安 1 NOS ≈ 33時間 shelter、$5 ≈ 1週間連続稼働 |
| W3 | PM 決着 2026-07-29 | 含み益 +$1.12 が realized に。loop 設置済み・自動 |
| W4 | 上流 PR [#82](https://github.com/BlockRunAI/blockrun-mcp/pull/82) のレビュー | merge されれば買い手の目の前に rail が並ぶ |
| W5 | final runtime `72zCpJEZ…` が自然に 21600秒 ceiling の replacement margin へ入る | force-once ではなく wall-clock trigger で list→verify→旧 state 2 を再readbackし、証拠の最後の穴を閉じる。実装順は止めず TASKMARKET-READBACK-1 を進める |

### G0. 上流 PR — 我々の rail を買い手のいる場所へ（2026-07-27）

**[BlockRunAI/blockrun-mcp#82](https://github.com/BlockRunAI/blockrun-mcp/pull/82) 提出済み**: `blockrun_nosana`（rent/status/extend）。上流は **Solana を既に一級市民として持っていた**（`getChain()` / `SolanaLLMClient` / `solana-402.ts`）が **Nosana への言及はゼロ** — 新 chain ではなく新しい取引先を足すだけで済んだ。

| 判断 | 理由 |
|---|---|
| `optionalDependencies` ではなく **optional peer** | npm は optional deps を既定で入れる。ほとんどの人が呼ばないツールのために全員に113パッケージ払わせない。`package-lock.json` は無改変 |
| 事前に断る3つ（範囲外の秒数 / 予算超過 / array `cmd`） | 全部こちらが実際に踏んだ失敗。特に array `cmd` は SDK が受理してノードが数秒後に**無言で死ぬ** |
| 説明文に「NOS と SOL を持つ必要」「定義は公開 IPFS に載る」を先に書く | 後から気づかせない |

**検証**: 262/262 tests・typecheck・build・brand-numbers check・CONTRIBUTING の stdio smoke（20 tools に `blockrun_nosana` 在り）。加えて **mock ではなく live mainnet market に打った** — `jobs.get` が `state: RUNNING, timeout: 1200` を返し、`getExposeIdHash` が実際に稼働中の URL と一致。

**リスク（一次調査）**: この repo で外部 fork の PR が**そのまま merge された実績は直近ゼロ**。維持者のリリース速度が極端に速く、内容だけ吸収されて PR は閉じられる形になりやすい（#59/#66 が実例、停滞と conflict が明示的な理由）。だから小さく・単一目的・最新 main に rebase 済みで出した。

## G. 稼ぎ loop を real にする（**待ち**。導線は作り終えた — 上の W1）

**この節は「着手待ち」ではなく「他人待ち」。** 商品も出品も discovery 登録も PR も終わっている。残る変数は「見知らぬ他人が払うか」だけで、こちらの作業量では動かない。だから優先順位表の番号からは外し、条件が満たされた瞬間に動く枠（W1）に置く。

**目標**: Franklin 1体の月コスト ≈ $35（lease 24/7）を、Franklin 自身の稼ぎで賄う。

| rail | 現状（実測） | real にするための残作業 |
|---|---|---|
| **yield** | ✅ Fluid に $5.10 @5.36% = 月$0.02 | 元本を増やすしかない。$35/月には元本 $7,800。**単独では届かない**が土台として維持 |
| **PM（Polymarket）** | 🟡 Fed ポジション **+$1.12** 含み益（curPrice 0.8325）、**決着 2026-07-29**。✅ **redeem 経路 verified 2026-07-27** | ①**7/29 に `redeem.py` を実行**（経路確認済み: `no redeemable conditions found — nothing to do` を正常返却）②✅ **allowance は既に MAX で解決済み**（実測 2026-07-27: spender `0xE1111800…`/`0xd91E80cF…`/`0xe2222d27…` すべて uint256 MAX）③✅ **資金もある: deposit wallet 内 collateral $8.24**（Polygon の raw USDC が 0 に見えたのは proxy 内 collateral だったため）④✅ **実 fill 達成 2026-07-27**: founder 鍵で LIVE run → `NAKED-FIX complete 8@0.168` が実約定。positions API 実測で **YES 8@0.6923 + NO 7.9761@0.1679** の2本 = 合計 **$0.86 で $1 が返る bundle** を保有（7/29 決着で市場リスクなしに +$1.12 確定）。**dry ゼロの実注文・実約定・on-chain 検証済み** ⑤✅ **loop 化 完了 2026-07-27**: `~/Library/LaunchAgents/ai.anicca.pm-live-trade.plist`（LIVE `run.sh`、`ANICCA_HOME=/Users/anicca/.anicca-founder` を env で固定、1時間ごと、log `~/.hermes/state/pm-live-trade.log`）。**kickstart で実発火を検証**: 市場 `Mubadala Citi DC Open` を YES 0.44 + NO 0.53 = 0.970（3.0% lock）と判定し、**YES 6@0.44 を実発注（ok=True status=live id=0x7e1c111f4e）**。NO 脚は `invalid post-only order: order crosses book` で拒否 = 板が動いた時の仕様どおりの挙動。**片脚は次パスの NAKED-FIX が閉じる = 自己修復ループとして噛み合っている**。旧 dry loop `ai.anicca.pm-decision-loop` は observe 専用のまま放置（LIVE はこちらが担当） |

**★ PM が「壊れていた」ことは一度も無かった（2026-07-27 判明）★**: 過去の LIVE run が `allowance not enough` で落ちたのは、**別 instance の鍵で走らせていたから**（blockrun の proxy を見ていた）。founder 鍵で見ると registered=true・allowance MAX・collateral $8.24。**教訓: 複数 instance がある環境では、失敗を機能の欠陥と診断する前に「どの identity で走らせたか」を必ず確認する。**
| **x402 売り** | 🔴 **商品が間違っていた（2026-07-27 市場実測で判明）** | 下記 G2 |
| **Hummingbot MM** | ⏸ capital-gated | 運用資本 $100+ に到達したら着手 |
| ✗ AutoHedge / Franklin-Trading / HL | 不採用（前者2つは執行コード無し、HL は Dais が OFF） | — |

**done 条件**: 30日間の入金合計 ≥ $35 が on-chain または入金台帳で確認できる。

### G2. x402 の商品を差し替える（2026-07-27）

**市場実測**（CDP Bazaar 200件）: 中央値 $0.005 だが **平均 $5.05・17% が $0.05以上・最大 $1000**。高単価帯で実際に売れているもの:

| 価格 | 売り物 |
|---|---|
| $1000 | 請求書決済（api.bitrefill.com） |
| $1.00 | RPC アクセス（QuickNode）／agent 実行（Apify）／トークン購入 |
| $0.50 | 株の判定・スクリーナー（stocktrends） |
| $0.28 | 人物データ補完（stableenrich） |
| $0.25 | ニュース取得 |

**共通点 = 「エージェントが自分では作れないデータ／能力」**。我々の現行商品（PII マスク $0.005）は正規表現で誰でも自作できる commodity で、**買う理由が無い**。月$35 には 7,000 call 必要という時点で商品設計の失敗。

**差し替え先 = GPU box を x402 で貸す**。理由: ①原価 $0.008/10分 に対し市場価格帯は $0.50〜$1.00（粗利 98%）②**confidential 経路・cap 付き子財布・自己延長を実際に通したのは我々だけ**（TTY shim / flat string cmd / poster 常駐 / cap=残高 / SDK extend の5つの非自明な壁を実測で解いた）③買い手＝「所有者のラップトップから逃げたいエージェント」で、x402 で払える相手そのもの。

**MVP ✅ 達成 2026-07-27**: `POST /rent-a-box`（$0.50、live: `anicca-x402-discovery-production.up.railway.app`）。実測 E2E: 決済 **tx `0x0bc2fe2bef2e…` success** → service が Nosana に job **`Fnf4KFc6APBXw2kQ1XzQf8fFC8sSu1g2arDjoyY9NcLC`** を建て（payer = cap 付き sub-wallet `71Ffq…`、timeout 600）→ 返した公開 URL `https://2A5JG64j5rFL7aBL88FpJMEcWG5d7tSEUfhYDt2aAcmp.node.k8s.prd.nos.ci` が **HTTP 200**。**粗利 98%**（売価 $0.50 / 原価 $0.008）。

実装: `apps/x402-agents/src/rent-a-box.mjs`（9/9 tests）+ server-lite への route/openapi 配線。設計要点: **借り手の box は我々の秘密を含まないので confidential 不要 → poster 常駐も不要 → web service から直接 post できる**（これが laptop 依存を切り離す鍵）。安全: 支払いは cap 付き sub-wallet（残高＝上限）、image は正規表現で検証、最大60分。潰したバグ: `Number(x || default)` が `durationMinutes:0` を default 10 に化けさせていた（`??` に修正）。

**価格を市場に合わせた（2026-07-27）**: 競合 **AgentMetal**（agentmetal.dev、awesome-x402 掲載）が Linux VPS を **$1.20/日**で貸している。我々の $0.50/10分 は日額換算 **$72 = 60倍高い**（しかも我々の原価 $1.15/日 ≈ 相手の売価）。→ **$0.10/10分 に値下げ**（原価比12倍・粗利92%）、live 実測で 402 amount=100000 を確認。差別化は価格でなく **①GPU（相手は CPU）②Solana 財布も NOS も不要で Base USDC 1回で URL が返る③秒で使える（SSH 不要）**。

**露出（done）**: ①x402scan に box 商品を登録（`27d2e00c…`、HTTP 200 success）②**awesome-x402 に掲載 PR** → https://github.com/xpaysh/awesome-x402/pull/1012（268★・買い手が実際に見に来る一覧）③CDP Bazaar は掲載確認済みだが**旧商品のみ**（box の決済後の index 待ち）。小規模一覧（3★/7★/0★）は労力に見合わないため見送り。

**経済の実測（2026-07-27）**: 受取 wallet `0x6592` の USDC = **$0.605**（$0.005+$0.50+$0.10 の3決済）。在庫消費は sub-wallet NOS 0.449（≈$0.117、大半は escrow で終了時に返る）→ **粗利 96%+**。※全て自己決済なので INV-7 により「稼ぎ」には計上しない。商品が値段どおり動く証明として扱う。

**在庫の制約（実務の穴、発見 2026-07-27）**: box 1台に escrow **0.3384 NOS** + CLI が要求する **最低 0.005 SOL** が要る。売れても在庫が無ければ供給できない。現在 NOS 1.089（3台ぶん）に補充したが **SOL 0.0042 が最低ラインを割っている**のが真のボトルネック。owner 側の SOL も薄く、fee floor gate が正しく補充を拒否した。**次の作業 = SOL の供給経路（Base→Solana bridge か、稼ぎからの自動補充）**。

**残 = 外部 buyer の初決済**（自己決済でない1件）。

### G3. 人間も俺も抜けた loop 3本（2026-07-27）

| loop | 間隔 | 何を自分で決めるか | 検証 |
|---|---|---|---|
| `ai.anicca.pm-live-trade` | 1h | 市場を探し、裁定幅を判定し、実発注する | kickstart で実オーダー `0x7e1c111f4e` を確認 |
| `ai.anicca.earn-watch` | 30m | ①外部売上の監視 ②**PM が redeemable になったら自分で redeem** ③Bazaar 掲載の確認 | 実行ログ `payee_usdc=0.605 pm_redeemable=0 bazaar_rentabox=yes` |
| `ai.anicca.reinvest` | 6h | 余剰（残高 − 運転準備金 $3）が最低投入額 $1 を超えたら **自動で yield に入れる** | 実行で `yield_hold liquid=3.892 reserve=3`（$0.892 は最低額未満なので正しく見送り）|

**redeem も再投資も、もう人間の判断を待たない。** 潰したバグ: launchd の PATH に `timeout` が無く reinvest script が即死していた（`timeout: command not found` → node 直呼びに変更）。

**revenue の宛先を修正**: 売上受取が `0x6592`（**CDP 管理で秘密鍵がローカルに無い = 稼いでも動かせない**）だったため、payTo を **founder `0x810F6D61…`（鍵がディスクにある）** に変更。これで売上がそのまま再投資 loop の入力になる。

**SOL 在庫についての訂正**: 「SOL 0.005 が在庫のボトルネック」は誤り。0.005 最低は **CLI の制約**であって、rent-a-box は **SDK 直呼び**なので手数料ぶん（~0.00001 SOL/tx）で足りる。実際 SOL 0.0045 で box 2台が建った。在庫の実制約は **NOS の escrow 0.3384/台**のみ（現在 1.089 = 3台ぶん）。

### 鍵と wallet の対応（2026-07-27 実測、SDK 導出で確定）

| instance | EOA | Polymarket proxy | 備考 |
|---|---|---|---|
| `~/.anicca-founder` | `0x810F6D61…` | **`0x904B50d2…`** | **勝ちポジションの持ち主**。Base USDC $4.99 も同じ EOA |
| `~/.automaton` / `BLOCKRUN_WALLET_KEY` | `0xB9dd3B67…` | `0x5357AC61…` | HL account と同一 EOA |
| `~/.blockrun` | `0x3EcCAD24…` | `0xda4b6E34…` | registered:true だが approve は `invalid authorization` |
| `.polymarket.json` 記載 | signer `0x99b3fE…` | deposit `0x4c176db1…` | 上記いずれとも別。旧識別子 |

**教訓**: `0x904B50` はローカルの EOA 鍵からは導出できない（proxy であって EOA ではない）。**SDK に deposit wallet を導出させて突合する**のが唯一の正しい特定法。

## F. 記事の状態（2026-07-26）

draft 2本を `docs/articles/` に用意済み。**publish は全部仕上がってから**（Dais 指示）。

| 言語 | ファイル | 字数 | gate |
|---|---|---|---|
| JP | `2026-07-26-ai-pays-its-own-rent-jp.md` | 15.9k | slop 0 / AI 自己申告 0 / 内部パス 0 |
| EN | `2026-07-26-ai-pays-its-own-rent-en.md` | 11.6k | em-dash 0 / 同上 |

タイトル: 「AIが自分の財布でサーバー代を払う仕組み。どこまで動いて、何がまだ足りないのか」/ "How an AI pays for its own server. What already works, and what is still missing"

**更新済み**: S15 達成に伴い「契約1本ぶんの生存」を削除し、「契約を自分で延長する」節（tx `2MQZhiR3…`、900→1500秒）を山場として追加。

**タイトルは要再検討**（Dais 2026-07-27 却下）。却下の履歴は `docs/articles/title-candidates.json`。実データ（HN 高スコア）が示した勝ち型は「エージェントが具体的に何をやらかしたか」の事件型だが、Dais の指示は**事件型ではなく「どうやって成立させたか」型**。両者を満たす候補を再探索する。

**publish は G 節（稼ぎ）が verified になってから**。稼ぎの数字が入った方が記事として強い。
