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
| 4 | S12 | Franklin 本体を Nosana へ | 🔄 **E2E 走行中 2026-07-26**。設計確定: sub-wallet が家賃 payer 兼 Franklin cloud 鍵（`.solana-session`=sub-wallet secret を confidential env で搬送、正本鍵は Mac を出ない）。branch `s12-franklin`: USDC leg + franklin-job.mjs + confidential-post.mjs（detached `--wait` poster）+ bin/citizen-franklin-up、98/98 tests。実測: USDC $0.025 fund（sig 2GkU2Ukj…）→ **confidential job `EGJ8SBtTUcbhSDRbEGTGVPsgfk56yty1DPhwraSPiMEE` post 成功**（poster pid 常駐、steward attach 済み）。発見: escrow 要求は duration 非依存で 0.3384 NOS 固定。CLI は最低 0.005 SOL も要求。**確定した3知見**: ①moveCursor TTY crash は NODE_OPTIONS preload shim（shim/tty-shim.cjs）で根治 — poster が --wait で完走生存 ②confidential の定義搬送は poster→node の HTTP POST（postJobDefinitionUntilSuccess）で、poster 生存中なら成功（J4FW で実証: retrieved→validated→container started） ③**cmd は array 不可**: ["sh","-c",script] は node 側で ~3s 死、フラット文字列 cmd は稼働（A/B: probe job `6ceJBBkf…` の "probe up" が poster に stream された）。franklin def を string cmd に修正済み。✅ **本体達成 2026-07-26**: job `3DUJeSYDZdDFmZXr4u3hDbxuztWXysokEemQzn4fgUxt` で **Franklin が Nosana container 内で実走** — npm install→鍵展開→`franklin start` 実行→model 応答を生成→proof server が外部公開 URL `https://3qrxT3AofDWoUYcxh1ktV8NCz5g72JK6oNU5XftfMoA4.node.k8s.prd.nos.ci` で応答（実測 fetch、証拠: specs/evidence/s12-proof-3DUJeSYD.txt）。家賃は sub-wallet が on-chain 支払い、秘密は confidential p2p のみ、heartbeat 4/4 PASS。**残ギャップ（S12b・資金待ち）**: cloud からの USDC 有料推論は BlockRun frontier の $5 デポジット床で reject（sub $0.025、Franklin 総資産 $0.032）— 資金ギャップでありアーキテクチャは開通済み（qwen3 無償 tier は cloud から応答取得成功）。稼ぎ track（T2b/E7）が解除条件 |
| 5 | S14 | 独立の最終テスト — Mac 側プロセスだけ停止し Nosana 側の単独生存を実測 | ✅ **完了 2026-07-26**（S12 と同時実証）。手順: Franklin job `3DUJeSYD…` 稼働中に Mac 側の poster(pid 89603) と steward を kill（20:02:41Z、`poster-dead` 確認）→ その後も cloud service URL は **HTTP 200 で Franklin proof を返し続け**、lease は `2 success` で完走（monitor 実測）。= Mac が消えても Nosana 上の Franklin は生存。他の Mac 稼働系は無傷 |

### B. 稼ぎ（$1.15/日 → 実 payout）

| 順 | ID | 内容 | 状態 |
|---|---|---|---|
| 6 | T2b | discovery catalog 登録 | 🔄 **実測で前提修正 2026-07-26**: 「到達可能だが発見不可能」は不正確 — 実測すると x402 skill route は production で **404**（`anicca-proxy-production.up.railway.app` は health 200 だが `/api/x402/<skill>` 未マウント）。discovery 対応 server コードは2実装存在（`anicca-rtdash/apps/x402-agents/src/server.js` = CDP facilitator + `declareDiscoveryExtension`、railway.toml あるが未 link；`life-manager-8i-cutover` の serve.mjs = founder wallet `0x810F6D61F7606dEEE2657d3083E150a222Bc29C5`、x402.org facilitator で 402 検証済みだが CDP Bazaar には非投入）。**真の壁 = ①永続 URL にデプロイ ②pre-settlement 登録（Bazaar/x402scan は settlement-driven で初回 settle 後しか index されない → x402scan/AgentCash の pre-settlement submit が必要）③Bazaar merchant lookup で自分の listing 確認**。**登録経路確定（research 実測 2026-07-26）**: CDP Bazaar READ `GET https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources`（無認証）で **0x810f = 14,413件中 0件＝確実に未発見**を確認。最安 pre-settlement 経路 = x402scan `POST https://www.x402scan.com/api/x402/registry/register {url}` + **0x810f ウォレットの SIWx 署名**（live https URL 必須、サーバが URL を実プローブ。x402scan と AgentCash は backend 共有で二重に効く）。手順: ①discovery-ready server を安定 https URL にデプロイ ②`curl` で 402 body 形を目視検証 ③x402scan 登録（SIWx）④self-buy 1件で CDP Bazaar 自動掲載も得る（best）。補強 = awesome-x402 へ PR 1行（$0）。done 条件 = Bazaar/x402scan lookup で自 listing が返る。**Task1 ✅ 実装+検証 2026-07-26**: DB不要 lite server（`anicca-rtdash/apps/x402-agents/src/server-lite.mjs`、branch `feature/t2b-x402-discovery`、pure-regex PII sanitizer 1 route、CDP/x402.org facilitator + `declareDiscoveryExtension`）。ローカル実測: unpaid POST→402 の `PAYMENT-REQUIRED` header を base64 decode = **payTo 0x810f + `extensions.bazaar` 確認**（registry probe が読む形）、4/4 tests。commit local 成立（lefthook 通過）だが anicca-products remote は read-only で **push 403**（コードは存在、mirror 権限のみの問題）。**payTo 訂正**: 実 earn wallet = **0x6592EB8EF820aBC092e8C3474fb2042dffCCEDc7**（rtdash x402-agents の config default、鍵 `WALLET_PRIVATE_KEY` がディスク=SIWx 署名可）。0x810f は 8i の旧 founder で rtdash に参照・鍵なし＝不採用。両 wallet とも Bazaar 未掲載を実測。**Task2 進行中**: Railway project `anicca-x402-discovery`（id 3d54de7b、workspace anicca）作成 + env セット（X402_WALLET_ADDRESS=0x6592, X402_NETWORK=eip155:8453, CDP creds, PORT=8080）→ **Task2 ✅ 達成 2026-07-26**。live URL = `https://anicca-x402-discovery-production.up.railway.app/prompt-sanitizer`、実測 402 decode = payTo 0x6592・network eip155:8453・asset USDC(0x833589)・$0.005・**bazaar discovery ext=True**。3 root cause を潰した（npm ci lock→nixpacks npm install / env 未注入→`--service` / `crypto is not defined`→webcrypto global 注入）。**Task3 進行中**: x402scan register（`scripts/x402scan-register.mjs`, siwe + throwaway EVM 署名）。判明: 0x6592 は **CDP 管理 wallet で EVM 秘密鍵はローカルに無い**（総当り確認）。だが SIWX は submitter-auth で **署名者=payTo 一致不要**（recipe 確定: message=SIWE numeric chainId 8453、提出=`SIGN-IN-WITH-X` header に base64 payload、issuedAt 5分・nonce single-use）→ throwaway EVM で **SIWX auth 通過**。次エラー = `no_discovery`（HTTP 404）: x402scan が resource を **GET probe** するが route は POST 専用で GET=404（実測: GET/OPTIONS/`/.well-known/x402` 全 404）。**GET-probe 仮説は棄却**（実 root cause: x402scan は resource を probe せず `GET {origin}/openapi.json` を取得し OpenAPI doc の `x-payment-info` を読む。@agentcash/discovery 1.7.5 実測）。修正 = `/openapi.json` 配信（structured price）。**Task3 ✅ 達成 2026-07-26**: deploy #7 後、`node scripts/x402scan-register.mjs` = **register HTTP 200 `success:true`**、resource id `3c716f96-a73c-45d2-8267-aea6c7dc0f5e`・originId `88527961…`・accepts{network base, $0.005, payTo 0x6592} が x402scan に永続化（server echo で確認）。SIWX は throwaway EVM 署名で通過。x402scan⇄AgentCash backend 共有で二重掲載。**残 Task4（任意・CDP Bazaar seeding）**: self-buy 1件で settlement-driven の CDP Bazaar にも自動掲載 — ただし Base-USDC payer wallet（≠0x6592, INV-7）が要り、現状 Base 側 payer 未整備。public browse read-API path は未特定（登録成否とは別）。**discovery の壁は開通**: endpoint が live + buyer-agent が browse する x402scan directory に登録済み | 🟡 endpoint 発見可能に |
| 7 | E7 | Gig を banked まで（実 payout rail） | 🔄 **実案件進行中・8/14 契約日待ち**（実測 2026-07-26）。coconala talkroom `17943244`（SNS運用代行・鹿革ブランド）= transaction_state **取引中**、artifact v23 納品済み・buyer 可視・acceptance PASS。**正式納品 2026-08-14**（契約5項目+KPI PDF）→ その検収で funnel 初 `paid`＝E7 の実体。現状 buyer_accepted/paid/settled すべて null、earnings.jsonl 空。gig loop 稼働中（launchd `hf-gig-pass` 他、本案件を維持、kickstart 済み）。**banked は 8/14 の client 検収依存で今は強制不能**（外部人間+未来日付、検索で越える壁でない）。この番号は日程が来るまで in_progress 保持 |
| 8 | F1 / T2 | トレードループを実 live に | 🔴 **実測: scheduled loop は DRY 固定**（2026-07-26）。`ai.anicca.pm-decision-loop.plist` が cadence だが `run_decision_loop.sh` は PM_DRY_RUN=0 も PM_LIVE_CONFIRM も設定せず「絶対 live にならない」＝observe+report のみ、earn-ledger 全 null（実 fill ゼロ）。LIVE 経路 `skills/earn/polymarket-trade/run.sh`（PM_DRY_RUN=0・cap MAX_BET_SIZE=$2/MAX_PASS_SPEND=$20 hard-fixed・adversary-reviewed・Polymarket wallet `0x4c176db1cd976E570fD35E92e0F6559e1Ba515Aa` deployed）は存在。**LIVE を1回実走 = 実注文を試行したが `allowance not enough → spender 0xe2222d`（Polymarket CTF Exchange）+ 閉じられない naked leg で fail-closed**。真の blocker = ①CTF Exchange への USDC/CTF allowance 未設定 ②既存 naked position ③scheduled loop が live 経路を叩いていない。done = allowance 設定 → naked 解消 → run.sh を cadence 化して実 fill 1件 |
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
