FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm install --production
COPY index-remote.js ./
EXPOSE 8808
CMD ["node", "index-remote.js"]
