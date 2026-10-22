FROM node:22-alpine

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .

EXPOSE 5173

# Development server on purpose: this image is for the demo stack, not production.
CMD ["npm", "run", "dev"]
