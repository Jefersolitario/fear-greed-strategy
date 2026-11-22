
## All configurations: annualised return on committed gross notional, % per year. Net = taker 5 bps + half-spread + funding. Late = every fill one bar later. p placebo = share of 1,000 random-pair portfolios with at least this net PnL.
| configuration | timing | gross | net | net 95% (block bootstrap) | Sharpe net | maker-fee case | spot-fee case | funding | placebo mean net | p placebo | PSR(0) | deflated Sharpe (N=24) | ES 5% day, bps | worst day | worst 5 days | max drawdown |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1h coint e1.5 | late | 3.6 | -2.6 | [-12.2, 6.8] | -0.19 | 2.5 | -4.8 | -0.24 | -7.5 | 0.099 | 0.328 | 0.000 | -135.7 | -1614.5 | -2056.4 | -3722 |
| 1h coint e1.5 | ontime | 7.4 | 1.2 | [-9.0, 11.4] | 0.08 | 6.2 | -1.0 | -0.25 | -6.6 | 0.022 | 0.577 | 0.000 | -136.1 | -1317.4 | -1750.4 | -3323 |
| 1h coint e2.0 | late | 1.7 | -3.1 | [-11.5, 5.2] | -0.27 | 0.8 | -4.8 | -0.23 | -5.8 | 0.198 | 0.257 | 0.000 | -116.3 | -1575.8 | -1837.2 | -4434 |
| 1h coint e2.0 | ontime | 4.3 | -0.6 | [-9.1, 8.2] | -0.05 | 3.4 | -2.2 | -0.23 | -5.1 | 0.065 | 0.455 | 0.000 | -116.5 | -1284.1 | -1512.0 | -3851 |
| 1h coint e2.5 | late | -1.2 | -5.1 | [-12.6, 2.0] | -0.58 | -2.0 | -6.4 | -0.22 | -4.4 | 0.617 | 0.056 | 0.000 | -99.2 | -1376.8 | -1496.3 | -4684 |
| 1h coint e2.5 | ontime | 1.0 | -2.9 | [-9.9, 4.4] | -0.33 | 0.2 | -4.2 | -0.21 | -3.9 | 0.354 | 0.204 | 0.000 | -97.2 | -1147.5 | -1215.1 | -4205 |
| 1h coint vol | late | 1.6 | -3.3 | [-10.7, 3.8] | -0.30 | 0.7 | -5.0 | -0.19 | -6.1 | 0.148 | 0.234 | 0.000 | -104.4 | -1576.3 | -1837.5 | -3920 |
| 1h coint vol | ontime | 4.2 | -0.7 | [-8.2, 6.8] | -0.06 | 3.3 | -2.4 | -0.18 | -5.6 | 0.057 | 0.440 | 0.000 | -104.7 | -1284.5 | -1512.1 | -3061 |
| 1h dist e1.5 | late | -0.1 | -5.3 | [-9.8, -0.8] | -1.02 | -1.0 | -7.2 | -0.12 | -2.5 | 0.783 | 0.008 | 0.000 | -68.3 | -179.9 | -345.4 | -3375 |
| 1h dist e1.5 | ontime | 0.3 | -5.0 | [-9.7, -0.3] | -0.95 | -0.6 | -6.9 | -0.12 | -2.0 | 0.798 | 0.012 | 0.000 | -69.4 | -176.0 | -390.0 | -3539 |
| 1h dist e2.0 | late | -0.2 | -4.3 | [-8.2, -0.3] | -0.94 | -0.9 | -5.8 | -0.05 | -2.6 | 0.714 | 0.013 | 0.000 | -60.1 | -126.4 | -261.2 | -2966 |
| 1h dist e2.0 | ontime | 0.1 | -4.0 | [-8.1, 0.2] | -0.87 | -0.6 | -5.6 | -0.05 | -2.4 | 0.712 | 0.020 | 0.000 | -60.3 | -128.9 | -315.9 | -3024 |
| 1h dist e2.5 | late | 0.9 | -2.4 | [-5.6, 1.1] | -0.63 | 0.4 | -3.6 | 0.03 | -2.1 | 0.541 | 0.068 | 0.000 | -49.2 | -127.4 | -214.9 | -2370 |
| 1h dist e2.5 | ontime | 1.3 | -2.0 | [-5.4, 1.4] | -0.54 | 0.8 | -3.3 | 0.03 | -2.1 | 0.506 | 0.102 | 0.000 | -48.6 | -120.6 | -214.8 | -2312 |
| 1h dist vol | late | -0.7 | -4.7 | [-8.4, -1.0] | -1.07 | -1.3 | -6.2 | -0.05 | -3.1 | 0.728 | 0.006 | 0.000 | -58.6 | -136.7 | -245.5 | -2859 |
| 1h dist vol | ontime | -0.5 | -4.5 | [-8.4, -0.6] | -1.02 | -1.2 | -6.1 | -0.05 | -2.7 | 0.755 | 0.008 | 0.000 | -58.6 | -126.1 | -300.2 | -2910 |
| 5mA coint e2.0 | late | 10.6 | -27.0 | [-42.6, -8.5] | -3.38 | 2.5 | -47.8 | 0.16 | -34.1 | 0.124 | 0.001 | 0.000 | -103.5 | -166.4 | -257.3 | -2795 |
| 5mA coint e2.0 | ontime | 11.1 | -26.5 | [-42.1, -8.3] | -3.27 | 3.0 | -47.3 | 0.21 | -32.8 | 0.151 | 0.001 | 0.000 | -104.3 | -161.6 | -272.2 | -2789 |
| 5mA dist e2.0 | late | -2.2 | -31.8 | [-41.7, -22.2] | -9.26 | -8.9 | -49.2 | 0.28 | -20.2 | 0.945 | 0.000 | 0.000 | -53.2 | -77.7 | -170.0 | -3138 |
| 5mA dist e2.0 | ontime | -2.1 | -31.7 | [-41.7, -22.0] | -9.35 | -8.7 | -49.1 | 0.28 | -18.3 | 0.966 | 0.000 | 0.000 | -52.5 | -77.7 | -164.2 | -3130 |
| 5mB coint e2.0 | late | -11.2 | -13.2 | [-22.7, -4.5] | -2.47 | -11.1 | -14.6 | 0.63 | -11.0 | 0.631 | 0.007 | 0.000 | -75.8 | -213.3 | -299.8 | -1178 |
| 5mB coint e2.0 | ontime | -11.3 | -13.3 | [-23.2, -4.3] | -2.47 | -11.2 | -14.7 | 0.62 | -11.1 | 0.637 | 0.007 | 0.000 | -76.6 | -229.1 | -317.2 | -1206 |
| 5mB dist e2.0 | late | -5.0 | -7.2 | [-13.1, -1.5] | -1.86 | -5.5 | -8.5 | 0.02 | -1.6 | 0.828 | 0.056 | 0.000 | -49.9 | -83.6 | -141.5 | -718 |
| 5mB dist e2.0 | ontime | -5.0 | -7.2 | [-13.0, -1.6] | -1.87 | -5.5 | -8.5 | 0.01 | -1.5 | 0.837 | 0.055 | 0.000 | -49.3 | -78.7 | -143.5 | -714 |
| 1h coint e2.0div (POST HOC) | late | 3.8 | -1.2 | [-5.5, 3.1] | -0.19 | 2.8 | -3.0 | -0.27 | -5.7 | 0.073 | 0.322 | 0.000 | -78.6 | -223.8 | -378.6 | -1471 |
| 1h coint e2.0div (POST HOC) | ontime | 5.2 | 0.2 | [-4.5, 4.9] | 0.03 | 4.2 | -1.5 | -0.27 | -5.1 | 0.044 | 0.531 | 0.000 | -76.5 | -177.5 | -359.1 | -1358 |
| 1h dist e2.0div (POST HOC) | late | 1.3 | -2.6 | [-7.2, 1.9] | -0.56 | 0.6 | -4.1 | -0.06 | -2.6 | 0.509 | 0.092 | 0.000 | -56.0 | -190.7 | -248.2 | -3126 |
| 1h dist e2.0div (POST HOC) | ontime | 2.2 | -1.7 | [-6.6, 3.2] | -0.36 | 1.5 | -3.2 | -0.07 | -2.4 | 0.414 | 0.195 | 0.000 | -55.0 | -180.5 | -237.1 | -3022 |

## Net PnL by calendar year, % of committed gross notional (taker costs and funding); placebo mean in brackets

| configuration (1h) | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|
| 1h_coint_e1.5_late | -7.6 (-17.7) | 22.1 (1.7) | 0.8 (-4.9) | -14.5 (-7.9) | -5.1 (-11.9) | -10.5 (-1.7) |
| 1h_coint_e1.5_ontime | -2.7 (-16.3) | 29.6 (3.3) | 2.4 (-3.9) | -13.6 (-7.5) | -4.1 (-12.4) | -5.0 (-0.4) |
| 1h_coint_e2.0_late | -2.8 (-12.4) | 20.1 (0.9) | -2.4 (-3.8) | -15.3 (-7.2) | -3.5 (-8.9) | -13.7 (-1.3) |
| 1h_coint_e2.0_ontime | 0.4 (-11.5) | 24.5 (2.1) | -0.7 (-3.1) | -15.1 (-6.9) | -2.7 (-9.5) | -9.6 (-0.2) |
| 1h_coint_e2.0div_late | -3.3 (-12.2) | 4.9 (0.9) | -5.2 (-3.9) | -0.1 (-6.8) | -4.9 (-9.0) | 1.7 (-1.3) |
| 1h_coint_e2.0div_ontime | -1.3 (-11.4) | 9.2 (2.1) | -4.4 (-3.1) | -1.1 (-6.5) | -5.0 (-9.6) | 3.9 (-0.2) |
| 1h_coint_e2.5_late | -4.4 (-8.4) | 13.6 (0.1) | -2.5 (-2.3) | -14.8 (-5.9) | -3.5 (-6.6) | -17.5 (-1.5) |
| 1h_coint_e2.5_ontime | -1.8 (-7.7) | 19.3 (0.8) | -2.7 (-1.8) | -13.8 (-5.7) | -2.5 (-6.9) | -14.8 (-0.5) |
| 1h_coint_vol_late | -3.2 (-12.8) | 15.9 (-0.5) | -5.7 (-3.0) | -11.4 (-6.9) | -2.2 (-10.0) | -12.1 (-1.6) |
| 1h_coint_vol_ontime | -1.0 (-12.1) | 19.0 (0.5) | -3.3 (-2.4) | -10.6 (-6.7) | -0.6 (-10.3) | -7.7 (-0.8) |
| 1h_dist_e1.5_late | -1.9 (-0.7) | -0.9 (7.0) | 1.3 (-4.9) | -7.9 (-2.0) | -10.1 (-13.0) | -10.5 (-0.3) |
| 1h_dist_e1.5_ontime | -0.4 (0.6) | 0.8 (8.0) | 2.4 (-4.5) | -8.7 (-1.8) | -10.4 (-13.2) | -11.8 (-0.3) |
| 1h_dist_e2.0_late | -0.1 (-3.5) | -1.2 (4.4) | 3.7 (-4.0) | -6.3 (-1.8) | -11.4 (-9.9) | -8.9 (-0.1) |
| 1h_dist_e2.0_ontime | 1.0 (-2.9) | -1.0 (5.0) | 4.8 (-3.4) | -7.4 (-1.6) | -11.0 (-10.3) | -9.3 (-0.1) |
| 1h_dist_e2.0div_late | 11.0 (-3.5) | -3.9 (4.7) | 1.7 (-3.8) | -6.4 (-2.0) | -13.6 (-9.8) | -3.8 (-0.5) |
| 1h_dist_e2.0div_ontime | 13.9 (-3.0) | -2.8 (5.3) | 2.2 (-3.3) | -7.6 (-1.7) | -13.0 (-10.3) | -2.4 (-0.6) |
| 1h_dist_e2.5_late | 1.6 (-2.9) | 2.7 (2.3) | 4.0 (-3.1) | -4.5 (-1.1) | -8.9 (-6.0) | -8.3 (-1.1) |
| 1h_dist_e2.5_ontime | 1.3 (-2.5) | 3.6 (2.5) | 5.0 (-2.7) | -4.2 (-1.3) | -8.6 (-6.5) | -8.6 (-1.2) |
| 1h_dist_vol_late | -1.6 (-3.9) | -2.3 (2.0) | 3.0 (-4.1) | -6.0 (-1.0) | -11.3 (-10.8) | -8.4 (0.3) |
| 1h_dist_vol_ontime | -0.5 (-3.2) | -2.4 (2.7) | 3.9 (-3.5) | -7.3 (-0.6) | -10.8 (-11.0) | -8.6 (0.2) |

| configuration (5mA) | 2025 | 2026 |
|---|---|---|
| 5mA_coint_e2.0_late | -3.7 (-2.9) | -22.9 (-30.7) |
| 5mA_coint_e2.0_ontime | -3.5 (-3.0) | -22.6 (-29.3) |
| 5mA_dist_e2.0_late | -2.0 (-3.1) | -29.3 (-16.8) |
| 5mA_dist_e2.0_ontime | -1.8 (-3.1) | -29.5 (-15.0) |

| configuration (5mB) | 2026 |
|---|---|
| 5mB_coint_e2.0_late | -10.8 (-9.0) |
| 5mB_coint_e2.0_ontime | -10.9 (-9.1) |
| 5mB_dist_e2.0_late | -5.9 (-1.3) |
| 5mB_dist_e2.0_ontime | -5.9 (-1.2) |

## Split in time (hourly): selection = days before 2024-01-01 (1035 days), evaluation = after (1035 days)
| | configuration | Sharpe net | net % per year |
|---|---|---|---|
| best on selection | 1h_coint_e1.5_ontime | 1.03 | 10.3 |
| the same on evaluation | 1h_coint_e1.5_ontime | -0.45 | -8.0 [-22.4, 6.7], p placebo 0.575 |

| configuration | Sharpe selection | Sharpe evaluation | net % per year, evaluation |
|---|---|---|---|
| 1h_coint_e1.5_late | 0.55 | -0.64 | -10.6 |
| 1h_coint_e1.5_ontime | 1.03 | -0.45 | -8.0 |
| 1h_coint_e2.0_late | 0.64 | -0.82 | -11.5 |
| 1h_coint_e2.0_ontime | 1.00 | -0.68 | -9.7 |
| 1h_coint_e2.5_late | 0.35 | -1.20 | -12.6 |
| 1h_coint_e2.5_ontime | 0.74 | -1.10 | -11.0 |
| 1h_coint_vol_late | 0.34 | -0.66 | -9.1 |
| 1h_coint_vol_ontime | 0.68 | -0.48 | -6.6 |
| 1h_dist_e1.5_late | -0.08 | -2.35 | -10.0 |
| 1h_dist_e1.5_ontime | 0.16 | -2.50 | -10.9 |
| 1h_dist_e2.0_late | 0.16 | -2.54 | -9.4 |
| 1h_dist_e2.0_ontime | 0.32 | -2.57 | -9.8 |
| 1h_dist_e2.5_late | 0.67 | -2.48 | -7.6 |
| 1h_dist_e2.5_ontime | 0.80 | -2.44 | -7.6 |
| 1h_dist_vol_late | -0.06 | -2.57 | -9.1 |
| 1h_dist_vol_ontime | 0.07 | -2.62 | -9.4 |

## Best of 16 configurations against the best-of-16 random-pair placebo [1h]: best Sharpe 0.08 (1h_coint_e1.5_ontime); placebo best-of median -0.04, 95th percentile 0.53; p = 0.368. Best net PnL 659 bps (1h_coint_e1.5_ontime), p = 0.297

## Best of 4 configurations against the best-of-4 random-pair placebo [5mA]: best Sharpe -3.27 (5mA_coint_e2.0_ontime); placebo best-of median -1.74, 95th percentile -0.58; p = 0.983. Best net PnL -2613 bps (5mA_coint_e2.0_ontime), p = 0.897

## Best of 4 configurations against the best-of-4 random-pair placebo [5mB]: best Sharpe -1.86 (5mB_dist_e2.0_late); placebo best-of median -0.14, 95th percentile 1.18; p = 0.995. Best net PnL -589 bps (5mB_dist_e2.0_late), p = 0.871

## Pairs selected most often [1h, dist]: 932 distinct pairs in 69 windows; 35% of them have positive total net PnL. PnL in bps of one leg's notional, summed over the windows in which the pair was selected.
| pair | times selected | gross | net | net, one bar late |
|---|---|---|---|---|
| BNB / BTC | 11 | 2801 | 2243 | 2576 |
| BTC / ETH | 8 | 1151 | 877 | 998 |
| EOS / ETC | 7 | 6286 | 5258 | 4777 |
| DOT / VET | 7 | 2163 | 1797 | 2532 |
| ATOM / DOT | 7 | 580 | 190 | 216 |
| ETH / LINK | 7 | 832 | 132 | -458 |
| LTC / XRP | 7 | -948 | -1303 | -1056 |
| ADA / DOT | 7 | -1275 | -1563 | -607 |
| BTC / LTC | 7 | -3458 | -3621 | -4010 |
| BCH / EOS | 6 | 3403 | 2966 | 2374 |
| FIL / SHIB | 6 | 3211 | 2709 | 1881 |
| BCH / LTC | 6 | 830 | 385 | -11 |

## Pairs selected most often [1h, coint]: 1294 distinct pairs in 69 windows; 37% of them have positive total net PnL. PnL in bps of one leg's notional, summed over the windows in which the pair was selected.
| pair | times selected | gross | net | net, one bar late |
|---|---|---|---|---|
| ATOM / GALA | 4 | 177 | -103 | -358 |
| ATOM / FTM | 3 | 2419 | 2117 | 2540 |
| DOGE / SHIB | 3 | 414 | 191 | -58 |
| ATOM / SHIB | 3 | 368 | 11 | -301 |
| FET / RENDER | 3 | 267 | -31 | 227 |
| ENJ / MANA | 3 | -425 | -715 | -639 |
| ADA / LINK | 3 | -723 | -875 | -1195 |
| DOT / NEAR | 3 | -1546 | -1887 | -1916 |
| CTXC / GXS | 2 | 5776 | 5642 | 5248 |
| KAVA / LRC | 2 | 5268 | 4911 | 5130 |
| FIL / ICP | 2 | 3910 | 3640 | 3098 |
| MEME / SAND | 2 | 3202 | 3024 | 3342 |

## Pairs selected most often [5mA, dist]: 400 distinct pairs in 144 windows; 25% of them have positive total net PnL. PnL in bps of one leg's notional, summed over the windows in which the pair was selected.
| pair | times selected | gross | net | net, one bar late |
|---|---|---|---|---|
| BNB / BTC | 79 | 781 | -1314 | -1582 |
| BTC / ETH | 70 | 1901 | -76 | -54 |
| ETH / SOL | 54 | -889 | -2459 | -2467 |
| ETH / LINK | 52 | -208 | -1935 | -2214 |
| AVAX / LINK | 48 | 324 | -1931 | -2354 |
| BTC / XRP | 47 | 862 | -507 | -804 |
| LINK / SOL | 46 | 1248 | -730 | -941 |
| DOGE / XRP | 45 | 612 | -665 | -759 |
| ADA / DOGE | 44 | 838 | -946 | -644 |
| BNB / SOL | 41 | -19 | -1314 | -1000 |
| ADA / LINK | 41 | -372 | -2089 | -1929 |
| DOGE / SOL | 40 | 48 | -1117 | -1241 |

## Pairs selected most often [5mA, coint]: 1192 distinct pairs in 144 windows; 36% of them have positive total net PnL. PnL in bps of one leg's notional, summed over the windows in which the pair was selected.
| pair | times selected | gross | net | net, one bar late |
|---|---|---|---|---|
| DOGE / PEPE | 37 | 935 | -816 | -886 |
| ADA / PEPE | 30 | 2099 | 329 | 136 |
| AVAX / PEPE | 30 | 1678 | -258 | -654 |
| PEPE / XRP | 30 | -85 | -1388 | -1271 |
| LINK / PEPE | 29 | 4194 | 1933 | 1436 |
| PEPE / SOL | 26 | -319 | -1583 | -1361 |
| PEPE / SUI | 25 | 811 | -669 | -1115 |
| LTC / PEPE | 20 | 2240 | 1089 | 1019 |
| BNB / PEPE | 20 | -1772 | -2742 | -2712 |
| BTC / PEPE | 17 | 1225 | 402 | 396 |
| ETH / PEPE | 17 | -66 | -1058 | -663 |
| PEPE / TAO | 16 | 1879 | 860 | 949 |

## Pairs selected most often [5mB, dist]: 107 distinct pairs in 10 windows; 28% of them have positive total net PnL. PnL in bps of one leg's notional, summed over the windows in which the pair was selected.
| pair | times selected | gross | net | net, one bar late |
|---|---|---|---|---|
| DOGE / XRP | 6 | 928 | 733 | 942 |
| BTC / XRP | 5 | 1429 | 1234 | 1295 |
| BNB / BTC | 5 | 745 | 617 | 589 |
| LINK / SOL | 5 | -6 | -144 | -123 |
| ADA / AVAX | 4 | 1777 | 1648 | 1781 |
| LTC / XRP | 4 | 966 | 752 | 772 |
| BNB / XRP | 4 | 493 | 380 | 294 |
| BTC / LINK | 4 | 99 | -109 | -119 |
| AVAX / LINK | 4 | -188 | -376 | -362 |
| AVAX / SOL | 4 | -516 | -626 | -641 |
| ADA / XRP | 4 | -1494 | -1600 | -1555 |
| BNB / ETH | 4 | -1593 | -1687 | -1585 |

## Pairs selected most often [5mB, coint]: 179 distinct pairs in 10 windows; 32% of them have positive total net PnL. PnL in bps of one leg's notional, summed over the windows in which the pair was selected.
| pair | times selected | gross | net | net, one bar late |
|---|---|---|---|---|
| BTC / SOL | 3 | 388 | 263 | 209 |
| LTC / SUI | 2 | 1077 | 874 | 1064 |
| LINK / LTC | 2 | 681 | 420 | 424 |
| AVAX / XRP | 2 | 460 | 356 | 509 |
| AVAX / SUI | 2 | 437 | 323 | 467 |
| LTC / SOL | 2 | 352 | 228 | 116 |
| SUI / XRP | 2 | 128 | 66 | 110 |
| ETH / SOL | 2 | 38 | -9 | -13 |
| LINK / SOL | 2 | -199 | -239 | -275 |
| DOGE / SOL | 2 | -302 | -358 | -396 |
| AVAX / BTC | 2 | -326 | -422 | -530 |
| LTC / PEPE | 2 | -335 | -489 | -472 |

## Hindsight check (hourly, base rule). Net % per year on committed gross notional
| method | selected in advance | the 20 best pairs of each window, chosen afterwards |
|---|---|---|
| dist | -4.0 | 553.3 |
| coint | -0.6 | 494.3 |

| method | rank correlation of a pair's net PnL in consecutive windows [95%] | next-window net PnL of this window's top decile, bps | of the other pairs | difference 95% | mean net PnL of all pairs per window, bps | share of pair-windows with net > 0 |
|---|---|---|---|---|---|---|
| dist | -0.000 [-0.014, 0.014] | -57.2 | -43.1 | [-60.4, 31.5] | -37.3 | 26% |
| coint | -0.010 [-0.018, -0.002] | -65.3 | -74.1 | [-30.3, 52.2] | -71.2 | 29% |

## Concentration: the largest number of the selected pairs of a window that share one coin
| bar | selection | windows | median | mean | max | windows where one coin is in 10 or more pairs | distinct coins per window (median) |
|---|---|---|---|---|---|---|---|
| 1h | dist | 69 | 5 | 4.7 | 7 | 0 | 19 |
| 1h | coint | 69 | 7 | 7.7 | 20 | 15 | 24 |
| 1h | dist_div | 69 | 1 | 1.0 | 1 | 0 | 40 |
| 1h | coint_div | 69 | 1 | 1.0 | 1 | 0 | 40 |
| 5mA | dist | 144 | 6 | 5.7 | 8 | 0 | 13 |
| 5mA | coint | 144 | 8 | 8.6 | 20 | 47 | 18 |
| 5mB | dist | 10 | 6 | 5.6 | 7 | 0 | 12 |
| 5mB | coint | 10 | 12 | 10.6 | 17 | 6 | 18 |

## Trades of the selected pairs (base rule). PnL in bps of one leg's notional
| bar | method | timing | trades | mean gross | mean cost | mean funding | mean net | share net > 0 | closed at 0 / stop / window end / delisted | median hold, hours | median volume of the thinner leg in the signal bar, USD | 10th percentile | both legs had a perpetual |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1h | dist | ontime | 1771 | 0.9 | 51.9 | -0.64 | -51.6 | 43% | 36% / 50% / 14% / 0% | 85.0 | 699407 | 130081 | 94% |
| 1h | dist | late | 1770 | -2.4 | 51.9 | -0.63 | -54.9 | 44% | 36% / 50% / 14% / 0% | 85.0 | 697229 | 130059 | 94% |
| 1h | coint | ontime | 1893 | 51.0 | 54.8 | -2.80 | -6.7 | 48% | 40% / 48% / 12% / 0% | 75.0 | 478268 | 73352 | 78% |
| 1h | coint | late | 1893 | 20.4 | 54.8 | -2.80 | -37.2 | 49% | 40% / 47% / 12% / 0% | 75.0 | 478268 | 73352 | 78% |
| 1h | dist_div | ontime | 1659 | 29.8 | 52.5 | -0.94 | -23.6 | 44% | 35% / 48% / 17% / 0% | 90.0 | 624889 | 105172 | 94% |
| 1h | dist_div | late | 1659 | 17.1 | 52.4 | -0.86 | -36.2 | 45% | 35% / 48% / 17% / 0% | 90.0 | 624889 | 105172 | 94% |
| 1h | coint_div | ontime | 1987 | 59.4 | 54.0 | -3.05 | 2.3 | 49% | 41% / 46% / 13% / 0% | 75.0 | 485716 | 69317 | 83% |
| 1h | coint_div | late | 1986 | 43.3 | 54.0 | -3.12 | -13.8 | 49% | 41% / 46% / 13% / 0% | 75.0 | 486218 | 70054 | 83% |
| 5mA | dist | ontime | 3434 | -2.4 | 34.4 | 0.32 | -36.4 | 44% | 35% / 43% / 22% / 0% | 11.8 | 93994 | 14985 | 95% |
| 5mA | dist | late | 3431 | -2.5 | 34.4 | 0.32 | -36.6 | 43% | 35% / 43% / 22% / 0% | 11.8 | 94107 | 15007 | 95% |
| 5mA | coint | ontime | 4104 | 10.7 | 36.3 | 0.20 | -25.5 | 45% | 41% / 47% / 13% / 0% | 7.4 | 48417 | 5997 | 94% |
| 5mA | coint | late | 4104 | 10.2 | 36.3 | 0.15 | -26.0 | 45% | 41% / 47% / 13% / 0% | 7.4 | 48417 | 5997 | 94% |
| 5mB | dist | ontime | 214 | -76.8 | 33.5 | 0.23 | -110.1 | 39% | 31% / 51% / 18% / 0% | 117.9 | 162497 | 20336 | 99% |
| 5mB | dist | late | 214 | -76.7 | 33.5 | 0.24 | -110.0 | 40% | 31% / 51% / 18% / 0% | 117.9 | 162497 | 20336 | 99% |
| 5mB | coint | ontime | 237 | -156.4 | 36.4 | 8.65 | -184.2 | 38% | 32% / 46% / 21% / 0% | 109.6 | 76112 | 5928 | 93% |
| 5mB | coint | late | 237 | -154.7 | 36.4 | 8.70 | -182.5 | 38% | 32% / 46% / 21% / 0% | 109.5 | 76112 | 5928 | 93% |

## Cointegration tests per window, Benjamini-Hochberg at 5% over all pairs of the universe
| bar | windows | pairs per window (median) | pairs passing BH (median, mean, max) | windows with none | selected pairs that pass (mean of 20) |
|---|---|---|---|---|---|
| 1h | 69 | 4371 | 8, 39.0, 316 | 13 | 10.5 |
| 5mA | 144 | 435 | 1, 7.3, 145 | 69 | 5.8 |
| 5mB | 10 | 364 | 2, 8.0, 62 | 4 | 4.5 |

## Overshoot and reversion after a Bitcoin shock: buy the 10 coins that fell most against beta x Bitcoin, short beta x Bitcoin, from one to two hours after the shock. Mean per event, bps of the coin leg [95%, bootstrap over weeks]
| events | hold | n | mean abnormal return of all coins in the shock window | of the 10 picked | gross | net taker | net maker-fee case | share of events net > 0 | placebo gross (random hours) | p vs placebo | cross-sectional slope of later return on shock-window abnormal return | all coins hedged, gross |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A_1min_down | 4 h | 104 | -14.5 | -334.5 | 34.8 [-4.3, 82.1] | -8.0 [-46.5, 40.5] | 26.9 [-11.6, 72.6] | 49% | 2.7 | 0.011 | -0.043 [-0.094, 0.007] | 17.7 [-10.3, 48.6] |
| A_1min_down | 24 h | 104 | -14.5 | -334.5 | 112.2 [43.2, 183.7] | 73.3 [6.7, 145.4] | 108.2 [39.0, 178.5] | 52% | -11.0 | 0.001 | -0.081 [-0.198, 0.033] | 63.5 [-2.5, 134.1] |
| A_1min_down | 72 h | 104 | -14.5 | -334.5 | 67.5 [-109.5, 241.4] | 36.4 [-139.1, 211.1] | 71.3 [-100.9, 238.6] | 50% | -49.6 | 0.034 | -0.151 [-0.340, 0.029] | 84.0 [-89.2, 259.2] |
| B_hourly_down | 4 h | 118 | 6.7 | -334.3 | 51.7 [-2.9, 100.6] | 8.3 [-50.8, 59.6] | 43.6 [-11.1, 92.1] | 55% | 2.7 | 0.000 | -0.075 [-0.117, -0.033] | 29.5 [-6.4, 64.7] |
| B_hourly_down | 24 h | 118 | 6.7 | -334.3 | 122.4 [11.9, 223.4] | 82.3 [-31.3, 182.0] | 117.6 [6.4, 219.2] | 58% | -11.0 | 0.000 | -0.126 [-0.239, -0.011] | 81.3 [6.9, 156.8] |
| B_hourly_down | 72 h | 118 | 6.7 | -334.3 | 95.0 [-78.6, 266.9] | 64.1 [-109.3, 231.7] | 99.4 [-74.3, 273.4] | 53% | -49.6 | 0.007 | -0.186 [-0.368, -0.020] | 70.9 [-72.6, 211.1] |
| A_1min_up_mirror | 4 h | 100 | -65.0 | 312.6 | -12.0 [-53.2, 25.5] | -57.7 [-98.5, -19.9] | -22.9 [-64.3, 13.9] | 43% | 2.7 | 0.854 | 0.008 [-0.055, 0.079] | 10.0 [-18.8, 44.1] |
| A_1min_up_mirror | 24 h | 100 | -65.0 | 312.6 | 20.8 [-79.8, 129.2] | -31.7 [-133.7, 75.7] | 3.2 [-100.0, 114.2] | 48% | -11.0 | 0.189 | -0.073 [-0.228, 0.073] | -18.1 [-93.0, 59.3] |
| A_1min_up_mirror | 72 h | 100 | -65.0 | 312.6 | 85.1 [-102.8, 262.2] | 14.4 [-169.9, 193.2] | 49.3 [-148.5, 228.1] | 54% | -49.6 | 0.019 | -0.045 [-0.267, 0.158] | -11.1 [-160.6, 164.0] |
| B_hourly_up_mirror | 4 h | 123 | -118.6 | 287.8 | 22.2 [-14.5, 61.0] | -21.7 [-59.8, 19.8] | 12.8 [-27.3, 53.9] | 39% | 2.7 | 0.055 | -0.055 [-0.109, 0.005] | -3.6 [-40.9, 28.8] |
| B_hourly_up_mirror | 24 h | 123 | -118.6 | 287.8 | -16.6 [-92.4, 60.6] | -63.7 [-139.0, 15.9] | -29.2 [-108.0, 49.1] | 41% | -11.0 | 0.553 | -0.018 [-0.125, 0.086] | 18.3 [-41.2, 78.2] |
| B_hourly_up_mirror | 72 h | 123 | -118.6 | 287.8 | -187.4 [-327.6, -37.7] | -244.1 [-391.2, -93.5] | -209.6 [-345.1, -61.9] | 38% | -49.6 | 0.994 | -0.031 [-0.224, 0.154] | 145.8 [37.1, 249.3] |

## The same events: what the hedge did, and size. Means per event, bps
| events | hold | Bitcoin over the hold | the 10 coins unhedged | hedged gross | all coins unhedged | mean beta of the 10 | mean liquidity rank of the 10 | median hourly volume of the 10 at the decision, USD | events where the thinnest of the 10 traded under 100,000 USD in that hour |
|---|---|---|---|---|---|---|---|---|---|
| A_1min_down | 4 h | 10.7 | 42.2 | 34.8 | 30.2 | 1.23 | 52 | 1455529 | 24% |
| A_1min_down | 24 h | 73.1 | 187.6 | 112.2 | 150.6 | 1.23 | 52 | 1455529 | 24% |
| A_1min_down | 72 h | 114.8 | 206.0 | 67.5 | 230.7 | 1.23 | 52 | 1455529 | 24% |
| B_hourly_down | 4 h | 4.7 | 64.6 | 51.7 | 39.2 | 1.21 | 55 | 1740677 | 14% |
| B_hourly_down | 24 h | 74.0 | 212.2 | 122.4 | 182.1 | 1.21 | 55 | 1740677 | 14% |
| B_hourly_down | 72 h | 94.3 | 203.4 | 95.0 | 198.2 | 1.21 | 55 | 1740677 | 14% |
| placebo | 4 h | 1.6 | 4.8 | 2.7 | 2.9 | 1.31 | 52 | 641094 | 44% |
| placebo | 24 h | 18.8 | 9.9 | -11.0 | 20.1 | 1.31 | 52 | 641094 | 44% |
| placebo | 72 h | 38.4 | -9.1 | -49.6 | 18.2 | 1.31 | 52 | 641094 | 44% |

## The 24-hour result under pressure (primary event set and the hourly-event set). bps per event
| events | n | mean net | median net | mean net without the 5 best events | without the 5 best and 5 worst | share of total net PnL from the 5 best | funding: Bitcoin short | funding: coin longs | coins bought that had a perpetual | net if the coins are bought on spot (10 bps fee, no coin funding) | net if the coins' half-spread is twice the assumption [95%] | thinnest of the 10 coins, hourly volume at the decision: median USD | events where it is under 100,000 / 50,000 / 20,000 USD |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A_1min_down | 104 | 73.3 | 21.8 | 20.6 | 56.0 | 73% | 3.88 | 1.09 | 86% | 62.2 | 56.8 [-15.6, 129.5] | 237401 | 24% / 11% / 4% |
| B_hourly_down | 118 | 82.3 | 37.1 | 26.3 | 93.6 | 69% | 2.43 | 1.62 | 73% | 70.7 | 65.2 [-44.1, 169.9] | 348236 | 14% / 3% / 0% |

| events | hold | net, early part (n) | net, late part (n) | median net | worst event |
|---|---|---|---|---|---|
| A_1min_down | 4 h | -12.7 (75) | 4.3 (29) | -5.7 | -777.7 |
| A_1min_down | 24 h | 74.4 (75) | 70.5 (29) | 21.8 | -917.1 |
| A_1min_down | 72 h | 55.2 (75) | -12.2 (29) | -8.5 | -1946.2 |
| B_hourly_down | 4 h | 11.8 (85) | -0.9 (33) | 21.2 | -1678.4 |
| B_hourly_down | 24 h | 76.2 (85) | 98.1 (33) | 37.1 | -2336.6 |
| B_hourly_down | 72 h | 110.6 (85) | -55.6 (33) | 48.9 | -4387.5 |
| A_1min_up_mirror | 4 h | -34.4 (61) | -94.2 (39) | -30.9 | -874.3 |
| A_1min_up_mirror | 24 h | -62.3 (61) | 16.0 (39) | -16.4 | -1654.5 |
| A_1min_up_mirror | 72 h | -32.5 (61) | 87.8 (39) | 60.4 | -2484.7 |
| B_hourly_up_mirror | 4 h | -6.6 (88) | -59.8 (35) | -36.4 | -874.3 |
| B_hourly_up_mirror | 24 h | -54.5 (88) | -86.7 (35) | -70.9 | -1464.8 |
| B_hourly_up_mirror | 72 h | -287.2 (88) | -135.7 (35) | -205.3 | -3433.0 |

## Speed (prior P1): the same rule filled on time and one bar late; % per year on committed gross notional
| configuration | gross on time | gross late | net on time | net late | net lost by one bar of delay | Sharpe net on time | Sharpe net late |
|---|---|---|---|---|---|---|---|
| 1h_coint_e1.5 | 7.4 | 3.6 | 1.2 | -2.6 | 3.8 | 0.08 | -0.19 |
| 1h_coint_e2.0 | 4.3 | 1.7 | -0.6 | -3.1 | 2.5 | -0.05 | -0.27 |
| 1h_coint_e2.0div | 5.2 | 3.8 | 0.2 | -1.2 | 1.4 | 0.03 | -0.19 |
| 1h_coint_e2.5 | 1.0 | -1.2 | -2.9 | -5.1 | 2.2 | -0.33 | -0.58 |
| 1h_coint_vol | 4.2 | 1.6 | -0.7 | -3.3 | 2.6 | -0.06 | -0.30 |
| 1h_dist_e1.5 | 0.3 | -0.1 | -5.0 | -5.3 | 0.3 | -0.95 | -1.02 |
| 1h_dist_e2.0 | 0.1 | -0.2 | -4.0 | -4.3 | 0.3 | -0.87 | -0.94 |
| 1h_dist_e2.0div | 2.2 | 1.3 | -1.7 | -2.6 | 0.9 | -0.36 | -0.56 |
| 1h_dist_e2.5 | 1.3 | 0.9 | -2.0 | -2.4 | 0.3 | -0.54 | -0.63 |
| 1h_dist_vol | -0.5 | -0.7 | -4.5 | -4.7 | 0.1 | -1.02 | -1.07 |
| 5mA_coint_e2.0 | 11.1 | 10.6 | -26.5 | -27.0 | 0.5 | -3.27 | -3.38 |
| 5mA_dist_e2.0 | -2.1 | -2.2 | -31.7 | -31.8 | 0.1 | -9.35 | -9.26 |
| 5mB_coint_e2.0 | -11.3 | -11.2 | -13.3 | -13.2 | -0.1 | -2.47 | -2.47 |
| 5mB_dist_e2.0 | -5.0 | -5.0 | -7.2 | -7.2 | -0.0 | -1.87 | -1.86 |

## Trade size. Share of the signal bar's quote volume (thinner leg) that one leg of the trade would be
| bar | method | trades | median volume of the thinner leg in the signal bar, USD | 1,000 USD as a share of it (median) | trades where 1,000 USD is above 1% of it | 10,000 USD as a share (median) | trades where 10,000 USD is above 1% |
|---|---|---|---|---|---|---|---|
| 1h | dist | 1771 | 699407 | 0.143% | 6.9% | 1.43% | 61.5% |
| 1h | coint | 1893 | 478268 | 0.209% | 13.7% | 2.09% | 73.2% |
| 5mA | dist | 3434 | 93994 | 1.064% | 51.5% | 10.64% | 91.3% |
| 5mA | coint | 4104 | 48417 | 2.065% | 68.8% | 20.65% | 97.1% |
| 5mB | dist | 214 | 162497 | 0.616% | 40.7% | 6.16% | 89.3% |
| 5mB | coint | 237 | 76112 | 1.314% | 57.8% | 13.14% | 96.2% |

## Net result when the assumed half-spreads (2 / 5 / 10 bps) are replaced by the measured cost of crossing today's spot order books (median coin of each tier; bps per side: 1,000 USD 0.8 / 2.9 / 7.9; 10,000 USD 1.3 / 5.3 / 17.7). % per year on committed gross notional
| configuration | timing | net, assumed costs | net at 1,000 USD per leg (main case) | at 1,000 USD, 75th-percentile coin | net at 10,000 USD per leg (reference) | at 10,000 USD, 75th-percentile coin |
|---|---|---|---|---|---|---|
| 1h coint e1.5 | late | -2.6 | -1.7 | -3.5 | -5.2 | -11.1 |
| 1h coint e1.5 | ontime | 1.2 | 2.0 | 0.2 | -1.5 | -7.3 |
| 1h coint e2.0 | late | -3.1 | -2.4 | -3.8 | -5.1 | -9.7 |
| 1h coint e2.0 | ontime | -0.6 | 0.1 | -1.3 | -2.6 | -7.1 |
| 1h coint e2.0div | late | -1.2 | -0.5 | -1.9 | -3.2 | -7.8 |
| 1h coint e2.0div | ontime | 0.2 | 0.9 | -0.5 | -1.8 | -6.4 |
| 1h coint e2.5 | late | -5.1 | -4.6 | -5.7 | -6.7 | -10.4 |
| 1h coint e2.5 | ontime | -2.9 | -2.3 | -3.5 | -4.5 | -8.1 |
| 1h coint vol | late | -3.3 | -2.6 | -4.0 | -5.3 | -10.0 |
| 1h coint vol | ontime | -0.7 | -0.0 | -1.4 | -2.8 | -7.4 |
| 1h dist e1.5 | late | -5.3 | -4.5 | -5.9 | -7.3 | -12.0 |
| 1h dist e1.5 | ontime | -5.0 | -4.2 | -5.6 | -7.0 | -11.7 |
| 1h dist e2.0 | late | -4.3 | -3.7 | -4.8 | -5.9 | -9.6 |
| 1h dist e2.0 | ontime | -4.0 | -3.4 | -4.6 | -5.6 | -9.3 |
| 1h dist e2.0div | late | -2.6 | -2.1 | -3.2 | -4.2 | -7.8 |
| 1h dist e2.0div | ontime | -1.7 | -1.1 | -2.2 | -3.3 | -6.9 |
| 1h dist e2.5 | late | -2.4 | -1.9 | -2.8 | -3.7 | -6.7 |
| 1h dist e2.5 | ontime | -2.0 | -1.5 | -2.5 | -3.3 | -6.4 |
| 1h dist vol | late | -4.7 | -4.1 | -5.2 | -6.2 | -9.8 |
| 1h dist vol | ontime | -4.5 | -3.9 | -5.0 | -6.1 | -9.6 |
| 5mA coint e2.0 | late | -27.0 | -19.4 | -23.4 | -27.1 | -38.5 |
| 5mA coint e2.0 | ontime | -26.5 | -18.9 | -22.8 | -26.6 | -38.0 |
| 5mA dist e2.0 | late | -31.8 | -25.9 | -28.8 | -31.3 | -39.7 |
| 5mA dist e2.0 | ontime | -31.7 | -25.8 | -28.7 | -31.2 | -39.6 |
| 5mB coint e2.0 | late | -13.2 | -12.6 | -12.9 | -13.2 | -14.0 |
| 5mB coint e2.0 | ontime | -13.3 | -12.8 | -13.0 | -13.3 | -14.1 |
| 5mB dist e2.0 | late | -7.2 | -6.7 | -6.9 | -7.1 | -7.7 |
| 5mB dist e2.0 | ontime | -7.2 | -6.7 | -6.9 | -7.1 | -7.7 |

wrote /home/claude/research/btc-alts/repo/research/btc-alts/out/p2/summary.json
