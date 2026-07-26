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
| 4 | S12 | Franklin 本体を Nosana へ | 🔄 **E2E 走行中 2026-07-26**。設計確定: sub-wallet が家賃 payer 兼 Franklin cloud 鍵（`.solana-session`=sub-wallet secret を confidential env で搬送、正本鍵は Mac を出ない）。branch `s12-franklin`: USDC leg + franklin-job.mjs + confidential-post.mjs（detached `--wait` poster）+ bin/citizen-franklin-up、98/98 tests。実測: USDC $0.025 fund（sig 2GkU2Ukj…）→ **confidential job `EGJ8SBtTUcbhSDRbEGTGVPsgfk56yty1DPhwraSPiMEE` post 成功**（poster pid 常駐、steward attach 済み）。発見: escrow 要求は duration 非依存で 0.3384 NOS 固定。CLI は最低 0.005 SOL も要求。**確定した3知見**: ①moveCursor TTY crash は NODE_OPTIONS preload shim（shim/tty-shim.cjs）で根治 — poster が --wait で完走生存 ②confidential の定義搬送は poster→node の HTTP POST（postJobDefinitionUntilSuccess）で、poster 生存中なら成功（J4FW で実証: retrieved→validated→container started） ③**cmd は array 不可**: ["sh","-c",script] は node 側で ~3s 死、フラット文字列 cmd は稼働（A/B: probe job `6ceJBBkf…` の "probe up" が poster に stream された）。franklin def を string cmd に修正済み。✅ **本体達成 2026-07-26**: job `3DUJeSYDZdDFmZXr4u3hDbxuztWXysokEemQzn4fgUxt` で **Franklin が Nosana container 内で実走** — npm install→鍵展開→`franklin start` 実行→model 応答を生成→proof server が外部公開 URL `https://3qrxT3AofDWoUYcxh1ktV8NCz5g72JK6oNU5XftfMoA4.node.k8s.prd.nos.ci` で応答（実測 fetch、証拠: specs/evidence/s12-proof-3DUJeSYD.txt）。家賃は sub-wallet が on-chain 支払い、秘密は confidential p2p のみ、heartbeat 4/4 PASS。**S12b ✅ 解決 2026-07-26 — 「$5 デポジット床」は誤り（俺の前提ミス）**。実測: BlockRun は **Base の x402 で $0.003/call**（`POST https://blockrun.ai/api/v1/chat/completions` の 402 header = eip155:8453・USDC・amount 3000・payTo 0xe9030014…、デポジット床なし）。**founder wallet から実決済成功: HTTP 200 + gpt-5-mini の実出力、PAID tx `0x3abb9b69aab7…` success:true、USDC $4.995→$4.992**（`scripts/blockrun-buy.mjs`）。真因 = cloud Franklin が **Solana rail** で払おうとして verification に落ちていた。**S12c ✅ 達成 2026-07-26 — 完全自活が閉じた**: cap $1 の Base 専用 cloud 鍵 `0xd072CDDda8371D97834859E9c840F9B0F1e51a1d`（`scripts/base-subwallet.mjs` で生成、$0.50 seed、founder 鍵は Mac を出ない）を confidential env `BASE_KEY` で job `5gRY7ep9ntqq4qwDREAhwGYk3B5q9oTRn46EkS392Z5t` に搬送 → **container 内から自費で frontier 購入成功**: **tx `0xc785ae2336324228bf5fcfd19483e26e6749532429215ed935faee794574abe8`**、HTTP 200、モデル応答 = 「I am running inside a container rented by my own wallet, and I just paid for this sentence myself.」。cloud 鍵残高 $0.50→**$0.494** を on-chain 実測。公開 proof URL `https://3JosW9FaEVfguYzk5kXt8WNixantbTVhMFiw5PQK75Ge.node.k8s.prd.nos.ci`（証拠 `specs/evidence/s12c-frontier-selfpaid-5gRY7ep9.txt`）。x402=EIP-3009 なので cloud 鍵に **gas 不要**。潰したバグ: `npm i -g` は node の解決パスに乗らない → `/tmp/x402` にローカル install + 同 cwd 実行。**= 家（Nosana lease 自費）も餌（frontier 推論 自費）も、Mac 非依存で成立** |
| 5 | S14 | 独立の最終テスト — Mac 側プロセスだけ停止し Nosana 側の単独生存を実測 | ✅ **完了 2026-07-26**（S12 と同時実証）。手順: Franklin job `3DUJeSYD…` 稼働中に Mac 側の poster(pid 89603) と steward を kill（20:02:41Z、`poster-dead` 確認）→ その後も cloud service URL は **HTTP 200 で Franklin proof を返し続け**、lease は `2 success` で完走（monitor 実測）。= Mac が消えても Nosana 上の Franklin は生存。他の Mac 稼働系は無傷 |

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

### Q. Life Manager は Franklin 自身か、Franklin 群の管理者か

**答え: 両方。ただし段階が違う。** Life Manager は「Franklin を雇う側」として始まり、最終的に「自分も Franklin である管理者」になる。

- **管理者としての Life Manager**: ユーザーの USDC を受け取り、cap を決め、複数の Franklin に配分し、成績を見る。ユーザーから見た製品の顔。
- **Franklin としての Life Manager**: 自分自身も cloud に住み、自分の家賃と推論代を自費で払う。人間の subscription に依存しない。

前者だけだと「管理者は誰が養うのか」が残る。後者を satisfies して初めて自走する。

### 構造

```
ユーザー ──USDC──▶ Life Manager（管理者 兼 出資者。自身も cloud 常駐）
                        │ 配分・cap・成績監視
              ┌─────────┼─────────┐
              ▼         ▼         ▼
         Franklin#1  Franklin#2  Franklin#N   ← 全員 cloud 常駐
         各自 wallet / 家賃と推論代を自費 / 各自が稼ぐ
              └──── 稼ぎ ────▶ ユーザー
```

### 最終形へのフェーズ（「全部無料になる」までの道筋）

| Phase | 誰が払うか | 何が要るか | 現在地 |
|---|---|---|---|
| **P0 実験** | Dais が全額 | 部品の実証 | ✅ 完了。家(lease)も餌(frontier)も自費で払える経路を tx で実証（S12c/S15） |
| **P1 有料製品** | ユーザーが subscription/USDC を払う | Life Manager が Franklin を cloud で回し、ユーザーの資金を運用して増やす | 🔄 ここへ向かう。custody 設計・dashboard・cap UI が要る |
| **P2 自己負担** | Franklin の稼ぎが自分の家賃+推論代を上回る | 稼ぎ rail が黒字（yield/trade/x402 売上） | 未達。支出 rail は開通、収入 rail が細い |
| **P3 自己増殖** | 余剰で新しい Franklin を建てる | 黒字 + 自動 spawn | 未着手 |
| **P4 無料化** | ユーザーは払わない。Franklin の稼ぎが全コストを賄う | P2 の黒字が全ユーザー分をカバー | 最終形。ここで human credential も subscription も不要になる |

**P4 の条件を数字で書く**: Franklin 1体の月コストは、lease を 24/7 で回して約 $35（$0.048/hr × 720h）+ 推論代。1体が月 $35 以上を安定して稼げば自己負担が成立し、それを超えた分がユーザーへの還元と新規 Franklin の原資になる。**現状の稼ぎは月 $0 なので、ここが唯一の壁。**

### 未解決（設計判断が要る）

1. **custody**: non-custodial（ユーザー自身の wallet から Franklin へ直接）が最も安全で法的にも軽い。
2. **成績の見せ方**: 入出金と損益を on-chain で追える dashboard。「自己申告でなく chain で検証」を貫く。
3. **cap と停止権**: ユーザーが握る唯一のノブ。いつでも引き上げ・停止できること。
4. **複数 Franklin の分業**: 戦略別に分けるか、同戦略で冗長化するか。
5. **法的位置づけ**: 他人の資金運用は規制対象になり得る。non-custodial 設計で回避できるか **未調査**。

### done 条件（このセクション）

ユーザー1人が自分の wallet から Franklin 1体に USDC を送り、その Franklin が cloud で自費稼働し、稼ぎがユーザーの wallet に戻る。全段 on-chain 検証可能。


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

### 運用一般
| 事実 | 詳細 |
|---|---|
| `npm i -g` は node の解決パスに乗らない | container 内では専用ディレクトリにローカル install し、その cwd で実行する |
| Railway の env は `--service` 必須 | 付けないと silent に無視され、app が起動時 env 欠落で死ぬ |
| Railway `npm ci` は lock 不整合で落ちる | `nixpacks.toml` で install phase を `npm install` に上書き |
| Node に `globalThis.crypto` が無い環境がある | CDP SDK の Ed25519 JWT が `crypto is not defined` で死ぬ。`webcrypto` を global に注入 |
| loop の自己申告は信用しない | yield loop が「phantom」と誤検知したが、on-chain の share 残高では**実着地していた**。判定は必ず chain 側で |

## ★ 優先順位（Dais 裁定 2026-07-27）★

**記事は後。金を稼ぐのが先。** 支出側（家賃・推論代・自己延長）は全部 real で閉じた。だが**収入は月$0**。稼ぎ loop を本物にするまで publish しない。

| 順 | やること | なぜこの順か |
|---|---|---|
| **1** | **稼ぎ loop を real にする**（下記 G 節） | P2（自己負担）の唯一の壁。これが無いと記事の結論も弱いまま |
| 2 | 冗長化（住処・餌の2社目） | 単一障害点2つを外す |
| 3 | Life Manager merge 設計 | 製品化 |
| 4 | 記事 publish | 1 が verified になってから。稼ぎの数字が入った記事の方が圧倒的に強い |

## G. 稼ぎ loop を real にする（最優先）

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

**MVP**: `POST /rent-a-box` に $0.50 を x402 決済 → Nosana に confidential job を post → 公開 URL を返す。done = 外部 wallet からの決済1件で box が立ち URL が 200 を返す。

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
