# 项目简介
[![Me on CSDN](https://img.shields.io/badge/若苗瞬-CSDN-blue)](https://blog.csdn.net/ddrfan?type=blog) [![Me on Bilibili](https://img.shields.io/badge/欢迎-bilibili-red?style=flat&logo=youtube)](https://space.bilibili.com/688222797)

**简体中文** | [English](README_en.md)

## 关于
> [!Note]
> 这是个基于[OpenCLI](https://github.com/jackwener/openCLI)的问答系统，继承了查询各种网站的功能。
> 因为需要身份的时候使用的是用户的个人凭证，所以叫《个人小助理》。
> WEBUI来自我的[企业知识库](https://github.com/ShionWakanae/Llamarkdown)项目。  

## 特点

本项目和直接使用OpenCLI命令行有什么区别？  

1. 用LLM判断并考虑调用OpenCLI的顺序和逻辑。
2. 用户只需要提出自己的问题或需求。

本项目和用Agent通过skill调用openCLI有什么区别？

1. 简化操作流程和数据结构，只能操作网站(site)类型。
2. 用在线LLM可以省很多Token。
3. 用本地LLM更容易Hold住，成功完成任务。
4. 也许相当于自行车对比汽车: 下坡省力，上坡省油。



![](res/cat_typing.gif)

---

# ⭐安装

## ℹ️（1）环境准备

1. 安装 `Node.js` 20+：[Node.js官方](https://nodejs.org/zh-cn)
2. 安装 `OpenCLI`: `npm install -g @jackwener/opencli` : 详情参考[仓库](https://github.com/jackwener/open-cli)。
3. 按照OpenCLI的文档配置好OpenCLI。

## ℹ️（2）仓库克隆
我自己用的环境是`python 3.10`，没测试过新的python版本。

1. 将仓库代码克隆到一个本地目录： 
`git clone https://github.com/ShionWakanae/llamaIndexSample.git`
1. 进入这个目录建立虚拟环境：`python -m venv venv`
2. 激活虚拟环境：`.\venv\scripts\activate`
3. 安装依赖：`pip install -r requirements.txt`

---

# ⭐使用
## ℹ️（1）参数配置

将`.env_sample`拷贝成`.env`，并修改其中的API地址密钥，各种模型配置（本地或在线），其它参数可保留原样，后根据实际情况修改，配置样例如下：
``` ini
STORAGE_SECRET=xxxxxx                       #输入任意的固定字符串

LLM_API_BASE=https://api.openai.com/v1      #本地或在线的OpenAI或兼容API地址
LLM_API_KEY=sk-xxxxx                        #密钥
LLM_MODEL=gpt-4.1-mini                      #模型名称

WEBUI_USERNAME=janedoe                      #WebUI用户名
WEBUI_PASSWORD=123456                       #WebUI密码

HOST=127.0.0.1                              #WebUI主机地址
PORT=7860                                   #WebUI端口

LANGUAGE=简体中文                            #人类语言的全程
```

## ℹ️（2）信息查询
### 命令行查询
``` shell
python .\src\open_cli.py '你的问题'          #比如：B站最热门的5条视频
```
### 浏览器查询
1. 启动WebUI服务。
``` shell
python .\src\open_web.py
```
2. 打开浏览器，访问`http://127.0.0.1:7860/` 发送问题进行基于OpenCLI的网站查询。  

![](res/webui.png)

![](res/webui_1.png)

---

# 视频演示
点击打开B站视频：

[![WebUI](https://i2.hdslb.com/bfs/archive/3b9b9e079c254a26c2759f86028e926d5ea981cf.jpg@308w_174h)](https://www.bilibili.com/video/BV1DNG86eEr3)

还有更多的视频更新，有需要请站内自行查看。


# 技术栈
![Python](https://img.shields.io/badge/-Python-silver?logo=Python)
![Node.js](https://img.shields.io/badge/-Node.js-silver?logo=Node.js)
![NiceGUI](https://img.shields.io/badge/NiceGUI-UI-silver?logo=Gradio)

# 环境支撑
![llama.cpp](https://img.shields.io/badge/-llama.cpp-blueviolet?logo=ollama)
![github](https://img.shields.io/badge/-github-navy?logo=github)
![acer](https://img.shields.io/badge/predator-acer-green?logo=acer)
![nvidia](https://img.shields.io/badge/rtx--4060ti16gb-5a3b92?logo=nvidia)
![Intel](https://img.shields.io/badge/i9--12900f-brown?logo=Intel)
![ChatGPT](https://img.shields.io/badge/OpenAI-ChatGPT-navy?logo=OpenAI)

# 授权许可
![license](https://img.shields.io/github/license/ShionWakanae/llamaIndexSample.svg "MIT license") 

> [!Important]
> 本项目基于MIT许可证开源，您可以在遵守许可证条款的前提下自由使用、修改和分发本项目的代码。
