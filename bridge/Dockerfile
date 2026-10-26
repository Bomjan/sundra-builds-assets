FROM golang:1.23-alpine AS build
WORKDIR /src
COPY go.mod main.go ./
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /bridge main.go
FROM alpine:3.21
RUN adduser -D -u 10001 bridge
USER bridge
WORKDIR /app
COPY --from=build /bridge /app/bridge
EXPOSE 8080
CMD ["/app/bridge"]
