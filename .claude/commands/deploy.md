# 部署到服务器

执行以下步骤部署代码到腾讯云服务器：

1. 检查 git 状态，确认有修改需要提交
2. 如果有未提交的修改，提交代码（让用户确认 commit message）
3. 推送到 GitHub（git push origin main）
4. 检查 GitHub Actions 部署状态（gh run list --limit 1）
5. 等待部署完成，报告结果

注意：
- 部署通过 GitHub Actions 自动触发
- 服务器会自动 git pull 并运行 ./run.sh build
- 服务运行在端口 8081
