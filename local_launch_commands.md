# 前置环境

* 需要本地使用conda，已经安装好相关的包和库（这块在mac电脑arm架构下安装，会有一些坑）
* 有具体的conda env（可以参考下面的命令）
* 已经下载好huggingface的models（这里都可以参考原来的文档）

# 执行步骤

conda env list
conda activate /opt/anaconda3/env/chattts
python launch.py --use_cpu=all

这样本地的api server就启动了