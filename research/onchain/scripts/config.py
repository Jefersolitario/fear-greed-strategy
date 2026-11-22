"""Fixed analysis constants (PREREG.md sections C-G)."""
import numpy as np

SEED = 20261122
HORIZONS = (1, 7, 30)
HAC_LAG = {1: 5, 7: 12, 30: 58}
COST = 0.0010            # 10 bps per unit of position change
ANN = 365
B_REG, BLOCK_REG = 5000, 60
B_RULE, BLOCK_RULE = 2000, 30
MIN_OBS = 500
MIN_TRAIN_OOS = 365
STALE_MAX = 9            # decision day minus newest data date; 2 is normal

V_METRICS = {
    "btc": ["AdrActCnt", "AdrBalCnt", "TxCnt", "TxTfrCnt", "FeeTotNtv", "HashRate", "BlkCnt", "CapMVRVCur",
            "CapRealUSD", "Puell", "FlowInExNtv", "FlowOutExNtv", "NetFlowEx", "NVTAdj", "NVTAdj90",
            "TxTfrValAdjUSD", "SplyActPct1yr", "VelCur1yr"],
    "eth": ["AdrActCnt", "AdrBalCnt", "TxCnt", "TxTfrCnt", "FeeTotNtv", "BlkCnt", "CapMVRVCur", "CapRealUSD",
            "FlowInExNtv", "FlowOutExNtv", "NetFlowEx", "NVTAdj", "NVTAdj90", "TxTfrValAdjUSD", "SplyActPct1yr",
            "VelCur1yr"],
}
L_METRICS = {
    "btc": ["AdrActCnt", "AdrBalCnt", "TxCnt", "TxTfrCnt", "FeeTotNtv", "HashRate", "BlkCnt", "CapMVRVCur",
            "CapRealUSD", "Puell"],
    "eth": ["AdrBalCnt", "TxCnt", "TxTfrCnt", "FeeTotNtv", "BlkCnt"],
}
PRICE_BUILT = {"CapMVRVCur", "CapRealUSD", "Puell", "NVTAdj", "NVTAdj90", "TxTfrValAdjUSD", "VelCur1yr"}
PX = ["PX_M7", "PX_M30", "PX_DD", "PX_Z"]

D = lambda s: np.datetime64(s, "D")
SAMPLE = {
    "L": dict(start={"btc": D("2012-01-01"), "eth": D("2017-01-01")}, end=D("2026-05-23"), split=D("2021-01-01"),
              subperiods=[("..2020", None, D("2020-12-31")), ("2021-2023", D("2021-01-01"), D("2023-12-31")),
                          ("2024..", D("2024-01-01"), None)]),
    "V": dict(start={"btc": D("2020-01-25"), "eth": D("2020-01-25")}, end=D("2026-05-23"), split=D("2023-01-01"),
              subperiods=[("2020-2021", None, D("2021-12-31")), ("2022-2023", D("2022-01-01"), D("2023-12-31")),
                          ("2024..", D("2024-01-01"), None)]),
}
THETAS = (-1.0, -0.5, 0.0, 0.5, 1.0)
DIRS = (1, -1)
