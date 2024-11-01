#!/usr/bin/env python
# coding: utf-8

import torch
from darts.models import LightGBMModel  # 导入 TFT 模型
from sklearn.metrics import precision_score  # 用于计算精确率
import matplotlib.pyplot as plt  # 用于绘图
import optuna  # 用于超参数优化
from pathlib import Path  # 用于处理文件路径
import matplotlib

# 自定义设置
from config import TIMESERIES_LENGTH  # 导入时间序列长度配置
from load_data.multivariate_timeseries import generate_processed_series_data  # 导入数据加载函数
from utils.logger import logger  # 导入日志记录器
from models.params import get_pl_trainer_kwargs  # 导入训练参数配置函数

# 设置浮点数矩阵乘法精度
torch.set_float32_matmul_precision('medium')

# 常量定义
MODEL_NAME = "TFTModel"  # 模型名称
WORK_DIR = Path(f"logs/{MODEL_NAME}_logs").resolve()  # 工作目录
PRED_STEPS = TIMESERIES_LENGTH["test_length"]  # 预测步长
matplotlib.rcParams['font.sans-serif'] = ['SimHei']  # 设置字体为黑体
matplotlib.rcParams['axes.unicode_minus'] = False  # 解决坐标轴负号显示问题

# 准备训练和验证数据 (在循环外加载数据)
data = generate_processed_series_data('training')

# 定义设备 (GPU if available, else CPU)
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# 定义模型
def define_model(trial):
    """
    定义 LightGBMModel 并根据 Optuna Trial 建议的参数进行初始化。

    Args:
        trial: Optuna Trial 对象，用于建议超参数。

    Returns:
        LightGBMModel: 初始化的 LightGBMModel。
    """
    # 模型参数

    # LightGBM 回归器的参数
    lgbm_params = {
        "lags": trial.suggest_int("lags", 1, 64),
        "lags_past_covariates": trial.suggest_int("lags_past_covariates", 1, 64),
        "lags_future_covariates": [0, -1, -2],
        "output_chunk_length": trial.suggest_int("output_chunk_length", 1, min(20, PRED_STEPS)),
        "learning_rate": trial.suggest_float("learning_rate", 0.001, 0.1),
        "num_leaves": trial.suggest_int("num_leaves", 31, 256),
        "n_estimators": trial.suggest_int("n_estimators", 50, 500),
        "min_child_samples": trial.suggest_int("min_child_samples", 20, 100),
        "subsample": trial.suggest_float("subsample", 0.6, 1.0),
        "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
        "objective": "binary",
        "random_state": 42,
    }

    model = LightGBMModel(
        verbose=True,  # 关闭 LightGBM 的输出
        **lgbm_params
    )

    return model


def train_and_evaluate(model, data):
    """
    训练和评估 TFT 模型。

    Args:
        model: TFT 模型。
        data: 包含训练、验证和测试数据的数据字典。

    Returns:
        float: 精确率。
    """
    model.fit(
        series=data['train'][-300:],  # 使用部分训练数据
        past_covariates=data['past_covariates'],  # 过去的协变量
        future_covariates=data['future_covariates'],  # 未来的协变量
        val_series=data['val'],  # 验证数据
        val_past_covariates=data['past_covariates'],  # 验证集过去的协变量
        val_future_covariates=data['future_covariates'],  # 验证集未来的协变量
    )

    # 使用 backtest 进行回测
    backtest_series = model.historical_forecasts(
        series=data['test'],
        past_covariates=data['past_covariates'],
        future_covariates=data['future_covariates'],
        start=data['test'].time_index[- PRED_STEPS],
        forecast_horizon=1,  # 预测 horizon 为 1
        stride=1,  # 每一步进行回测
        retrain=False
    )

    # 计算精确度
    true_labels = data["test"][-PRED_STEPS:].values().flatten().astype(int)  # 真实标签
    print(data['test'].time_index[- PRED_STEPS])
    print(data["test"].time_index)
    print(data["test"][-PRED_STEPS:].time_index)
    print(backtest_series[-PRED_STEPS:].time_index)
    probabilities = backtest_series[-PRED_STEPS:].values().flatten()  # 预测概率
    binary_predictions = (probabilities > 0.5).astype(int)  # 二元预测

    precision = precision_score(true_labels, binary_predictions)  # 计算精确率
    logger.info(f"精度: {precision:.4%}")
    # 绘图 (可根据需要取消注释)
    data["test"].plot(label='实际值')
    backtest_series.plot(label='回测预测值', lw=3, color="red", alpha=0.5)  # 更醒目的回测线
    plt.title("TFT Model Backtest - Last 20 Steps")
    plt.legend()
    plt.show()
    plt.close()

    # 清理显存
    del model
    torch.cuda.empty_cache()

    return precision


def plot_metrics(train_loss, val_loss, pred_series, test_data):
    """
    绘制训练损失、验证损失和预测结果。

    Args:
        train_loss: 训练损失列表。
        val_loss: 验证损失列表。
        pred_series: 预测序列。
        test_data: 测试数据。
    """
    plt.figure()
    plt.plot(train_loss, label='训练损失')
    plt.plot(val_loss, label='验证损失')
    plt.legend()
    plt.show()

    plt.figure()
    test_data[-PRED_STEPS:].plot(label="实际数据")
    pred_series.plot(label="预测结果")
    plt.legend()
    plt.show()


def objective(trial):
    """
    Optuna 的目标函数，用于优化超参数。

    Args:
        trial: Optuna Trial 对象。

    Returns:
        float: 精确率，作为优化的目标。
    """
    model = define_model(trial)  # 定义模型
    precision = train_and_evaluate(model, data)  # 训练和评估模型
    logger.info(f"试验{trial.number}: 最佳准确率: {study.best_value:.4%}")  # 记录最佳精确率
    logger.info(f"当前准确率:{precision:.4%}；当前超参数： {trial.params}")  # 记录当前超参数
    return precision


if __name__ == '__main__':
    study = optuna.create_study(
        direction="maximize",  # 最大化精确率
        study_name="tftmodel-precision-optimization",  # 研究名称
        storage="sqlite:///data/optuna/optuna_study.db",  # 数据库路径
        load_if_exists=True  # 如果数据库存在则加载
    )
    study.optimize(objective, n_trials=50, n_jobs=1)  # 开始优化

    logger.info(f"Best hyperparameters: {study.best_params}")  # 输出最佳超参数
    logger.info(f"Best precision: {study.best_value:.4f}")  # 输出最佳精确率
