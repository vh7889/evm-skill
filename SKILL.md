---
name: evm-skill
description: 用于 EVM 链批量钱包与资产操作。需要生成钱包、批量分发/归集原生 gas 代币、批量分发/归集 ERC20 代币、批量合约调用、单钱包私钥 Bitget 路由 swap、失败重试、断点续跑时使用。
---

# EVM Skill

## 概述

这个 skill 用于 EVM 链批量操作，当前包含 7 个脚本：
- 批量生成钱包
- 批量分发 gas 代币
- 批量归集 gas 代币
- 批量分发 ERC20 代币
- 批量归集 ERC20 代币
- 批量闭源合约调用
- 单钱包 Bitget 路由 swap

## 运行环境

在 `evm-skill` 目录执行命令，先激活虚拟环境：

```bash
cd <你的skill目录>/evm-skill
source .venv/bin/activate
```

## 输出目录

- 钱包文件默认输出到：`output/wallet/`
- 日志文件默认输出到：`output/log/`

## 脚本

- `scripts/batch_generate_wallets.py`
  - 批量生成 1-n 个钱包
  - 输出 CSV：`output/wallet/wallet_YYYYMMDD_HHMMSS-项目名-钱包数量.csv`
- `scripts/batch_distribute_gas.py`
  - 主钱包批量分发原生代币（BNB/ETH 等）
- `scripts/batch_collect_gas.py`
  - 分发钱包批量归集原生代币到主钱包
- `scripts/batch_distribute_erc20.py`
  - 主钱包批量分发 ERC20 代币
- `scripts/batch_collect_erc20.py`
  - 分发钱包批量归集 ERC20 代币到主钱包
- `scripts/batch_call_contract.py`
  - 分发钱包批量调用指定合约（value=0，按给定 16 进制 calldata）
- `scripts/single_swap_bitget.py`
  - 单一私钥执行 Bitget 路由 swap（EVM）

## 1) 批量生成钱包

命令：

```bash
python scripts/batch_generate_wallets.py --project <项目名> --count <钱包数量>
```

参数说明：
- `--project`：项目名，会写入 CSV 文件名，例如 `pm`、`op`
- `--count`：生成钱包数量，必须 >= 1
- `--rpc`：可选，自定义链 RPC

示例：

```bash
python scripts/batch_generate_wallets.py --project pm --count 20
```

输出：
- 生成 CSV：`output/wallet/wallet_20260302_115448-pm-20.csv`
- 列：`序号,address,privateKey`

## 2) 批量分发 gas 代币（原生币）

命令（固定数量）：

```bash
python scripts/batch_distribute_gas.py \
  --main-private-key <主钱包私钥> \
  --wallet-csv <钱包CSV文件名> \
  --rpc <RPC地址> \
  --threads <线程数> \
  --amount <固定数量>
```

命令（范围数量）：

```bash
python scripts/batch_distribute_gas.py \
  --main-private-key <主钱包私钥> \
  --wallet-csv <钱包CSV文件名> \
  --rpc <RPC地址> \
  --threads <线程数> \
  --amount-min <最小值> \
  --amount-max <最大值>
```

示例（每个钱包固定 0.0005 BNB）：

```bash
python scripts/batch_distribute_gas.py \
  --main-private-key "$(cat ../wallet_test.txt)" \
  --wallet-csv output/wallet/wallets_first3.csv \
  --rpc https://bsc-dataseed.binance.org/ \
  --threads 3 \
  --amount 0.0005
```

## 3) 批量归集 gas 代币（原生币）

命令：

```bash
python scripts/batch_collect_gas.py \
  --main-address <主钱包地址> \
  --wallet-csv <包含私钥的钱包CSV> \
  --rpc <RPC地址> \
  --threads <线程数>
```

示例：

```bash
python scripts/batch_collect_gas.py \
  --main-address 0x7ec9369df94ccc890030ca9a54e1e9f6096da700 \
  --wallet-csv output/wallet/wallets_first3_with_pk.csv \
  --rpc https://bsc-dataseed.binance.org/ \
  --threads 3
```

## 4) 批量分发 ERC20 代币

命令（固定数量）：

```bash
python scripts/batch_distribute_erc20.py \
  --main-private-key <主钱包私钥> \
  --wallet-csv <钱包CSV文件名> \
  --token <ERC20合约地址> \
  --rpc <RPC地址> \
  --threads <线程数> \
  --amount <固定数量>
```

命令（范围数量）：

```bash
python scripts/batch_distribute_erc20.py \
  --main-private-key <主钱包私钥> \
  --wallet-csv <钱包CSV文件名> \
  --token <ERC20合约地址> \
  --rpc <RPC地址> \
  --threads <线程数> \
  --amount-min <最小值> \
  --amount-max <最大值>
```

可选参数：
- `--token-decimals <decimals>`：不填则自动链上读取

## 5) 批量归集 ERC20 代币

命令：

```bash
python scripts/batch_collect_erc20.py \
  --main-address <主钱包地址> \
  --wallet-csv <包含私钥的钱包CSV> \
  --token <ERC20合约地址> \
  --rpc <RPC地址> \
  --threads <线程数>
```

可选参数：
- `--token-decimals <decimals>`：不填则自动链上读取

## 6) 批量闭源合约调用

命令：

```bash
python scripts/batch_call_contract.py \
  --wallet-csv <包含私钥的钱包CSV> \
  --rpc <RPC地址> \
  --threads <线程数> \
  --contract <合约地址> \
  --data <16进制calldata>
```

示例：

```bash
python scripts/batch_call_contract.py \
  --wallet-csv output/wallet/wallet_20260302_150132-test-5.csv \
  --rpc https://bsc-dataseed.binance.org/ \
  --threads 3 \
  --contract 0x55d398326f99059fF775485246999027B3197955 \
  --data 0x095ea7b30000000000000000000000007ec9369df94ccc890030ca9a54e1e9f6096da700ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff
```

## 7) 单钱包 Bitget 路由 Swap（EVM）

命令：

```bash
python scripts/single_swap_bitget.py \
  --private-key <私钥> \
  --rpc <RPC地址> \
  --chain bnb \
  --from-contract <fromToken地址> \
  --to-contract <toToken地址> \
  --amount <固定数量>
```

可选参数：
- `--slippage <百分比>`：例如 `0.5` 表示 0.5%

## 通用规则（转账/归集/调用/swap 脚本）

重跑模式（5 个批量链上脚本通用）：
- `--mode all`：处理全部未成功钱包（默认）
- `--mode failed`：仅处理失败钱包
- `--mode pending`：仅处理未开始钱包

线程建议：
- 普通 RPC：建议 `1-5`
- 付费 RPC：按服务能力提高
- 所有交易脚本默认动态读取链上实时 `gasPrice`，也可用 `--gas-price-gwei` 手动指定

日志规则：
- 分发 gas 日志：`output/log/<钱包csv名>_gas_distribution_log.csv`
- 归集 gas 日志：`output/log/<钱包csv名>_gas_collect_log.csv`
- 分发 ERC20 日志：`output/log/<钱包csv名>_erc20_distribution_log.csv`
- 归集 ERC20 日志：`output/log/<钱包csv名>_erc20_collect_log.csv`
- 合约调用日志：`output/log/<钱包csv名>_contract_call_log.csv`
- 字段包含：`转出地址`、`接收地址`、`成功哈希`、`失败原因`、`时间`
- 未开始记录时间为空
- 运行中持续落盘，程序中断后可继续

注意：
- 归集脚本、合约调用脚本要求 `wallet-csv` 必须包含 `privateKey` 列
- gas 归集是扣除 gas 后归集剩余可转余额
- ERC20 归集是归集 token 全部余额，但每个分发钱包仍需有足够 gas 作为手续费
- Bitget swap 中 `amount` 是人类可读数量，不是 wei
