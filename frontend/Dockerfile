# ============ 开发阶段 ============
FROM node:22-alpine AS dev

# 使用 npmmirror 国内镜像
RUN npm config set registry https://registry.npmmirror.com

WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# ============ 生产构建 ============
FROM node:22-alpine AS builder

# 使用 npmmirror 国内镜像
RUN npm config set registry https://registry.npmmirror.com

WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
RUN npm run build

# ============ 生产运行 ============
FROM nginx:alpine AS production
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
