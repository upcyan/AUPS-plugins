# acme — acme.sh 证书签发

属性：依赖

acme.sh 证书签发（零依赖脚本）：申请/续期，脚本与证书落在面板目录。

## 功能

- **证书签发**：acme.sh 状态、安装/申请证书

## 面板页签

| 页签 | 说明 |
|---|---|
| 证书签发 | acme.sh 状态、安装/申请证书 |

## CLI

```bash
aups acme ...   # acme.sh 证书管理
```

## 安装

```bash
aups plugins market install acme
```

## 说明

依赖插件，为 nginx 等环境插件提供证书申请能力。使用零依赖的 acme.sh 脚本，脚本与证书均保存在面板目录。
