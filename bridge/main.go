package main

import (
 "bytes"
 "context"
 "crypto/rand"
 "crypto/sha256"
 "crypto/subtle"
 "encoding/hex"
 "encoding/json"
 "errors"
 "fmt"
 "io"
 "log"
 "mime/multipart"
 "net/http"
 "os"
 "path/filepath"
 "strings"
 "sync"
 "time"
)

const maxUpload = 12 << 20
type server struct { mu sync.Mutex; posts map[string]*post; client *http.Client; token, uploadKey, profile, pageID, publicBase, dir string }
type post struct { ID string `json:"id"`; ImageURL string `json:"image_url"`; SHA256 string `json:"sha256"`; Caption string `json:"caption,omitempty"`; Status string `json:"status"`; ProviderResponse string `json:"provider_response,omitempty"`; CreatedAt time.Time `json:"created_at"` }
func jsonReply(w http.ResponseWriter,status int,v any){w.Header().Set("Content-Type","application/json");w.WriteHeader(status);_ = json.NewEncoder(w).Encode(v)}
func (s *server) auth(next http.HandlerFunc) http.HandlerFunc{return func(w http.ResponseWriter,r *http.Request){provided:=strings.TrimPrefix(r.Header.Get("Authorization"),"Bearer ");if len(provided)!=len(s.token)||subtle.ConstantTimeCompare([]byte(provided),[]byte(s.token))!=1 {jsonReply(w,401,map[string]string{"error":"unauthorized"});return};next(w,r)}}
func randomID() string {b:=make([]byte,16);if _,err:=rand.Read(b);err!=nil {panic(err)};return hex.EncodeToString(b)}
func (s *server) upload(w http.ResponseWriter,r *http.Request){
 if r.Method!=http.MethodPost {http.Error(w,"method not allowed",405);return}
 r.Body=http.MaxBytesReader(w,r.Body,maxUpload)
 if err:=r.ParseMultipartForm(maxUpload);err!=nil {jsonReply(w,400,map[string]string{"error":"invalid multipart upload"});return}
 file,_,err:=r.FormFile("image");if err!=nil {jsonReply(w,400,map[string]string{"error":"image field required"});return};defer file.Close()
 data,err:=io.ReadAll(io.LimitReader(file,maxUpload+1));if err!=nil||len(data)>maxUpload {jsonReply(w,413,map[string]string{"error":"image too large"});return}
 if len(data)<24||!bytes.Equal(data[:8],[]byte{137,80,78,71,13,10,26,10}) {jsonReply(w,400,map[string]string{"error":"PNG required"});return}
 // PNG IHDR width/height at bytes 16..23; verify 1080x1350.
 if !bytes.Equal(data[16:24],[]byte{0,0,4,56,0,0,5,70}) {jsonReply(w,400,map[string]string{"error":"image must be 1080x1350"});return}
 sum:=sha256.Sum256(data);digest:=hex.EncodeToString(sum[:]);id:=randomID();filename:=id+".png"
 if err:=os.WriteFile(filepath.Join(s.dir,filename),data,0600);err!=nil {jsonReply(w,500,map[string]string{"error":"storage failed"});return}
 p:=&post{ID:id,ImageURL:s.publicBase+"/media/"+filename,SHA256:digest,Status:"uploaded",CreatedAt:time.Now().UTC()}
 s.mu.Lock();s.posts[id]=p;s.mu.Unlock();jsonReply(w,201,p)
}
func (s *server) media(w http.ResponseWriter,r *http.Request){
 if r.Method!=http.MethodGet {http.Error(w,"method not allowed",405);return}
 id:=strings.TrimPrefix(r.URL.Path,"/media/")
 if len(id)!=36||!strings.HasSuffix(id,".png") {http.NotFound(w,r);return}
 http.ServeFile(w,r,filepath.Join(s.dir,id))
}
func (s *server) publish(w http.ResponseWriter,r *http.Request){
 if r.Method!=http.MethodPost {http.Error(w,"method not allowed",405);return}
 id:=strings.TrimPrefix(r.URL.Path,"/api/posts/")
 if len(id)!=32 {http.NotFound(w,r);return}
 var input struct {Caption string `json:"caption"`}
 if err:=json.NewDecoder(io.LimitReader(r.Body,16000)).Decode(&input);err!=nil||strings.TrimSpace(input.Caption)==""||len(input.Caption)>4000 {jsonReply(w,400,map[string]string{"error":"caption required (max 4000 chars)"});return}
 s.mu.Lock();p:=s.posts[id];if p==nil {s.mu.Unlock();http.NotFound(w,r);return}
 if p.Status!="uploaded" {s.mu.Unlock();jsonReply(w,409,map[string]string{"error":"already submitted or outcome uncertain; manual reconciliation required"});return}
 p.Status="submitting";p.Caption=input.Caption;url:=p.ImageURL;s.mu.Unlock()
 // Submit once. Any timeout or ambiguous result remains non-retryable until reconciled.
 body:=&bytes.Buffer{};writer:=multipart.NewWriter(body)
 fields:=map[string]string{"user":s.profile,"platform[]":"facebook","title":input.Caption,"facebook_page_id":s.pageID,"photos[]":url,"async_upload":"false"}
 for k,v:=range fields {_=writer.WriteField(k,v)};_ =writer.Close()
 ctx,cancel:=context.WithTimeout(r.Context(),90*time.Second);defer cancel()
 req,err:=http.NewRequestWithContext(ctx,"POST","https://api.upload-post.com/api/upload_photos",body)
 if err!=nil {jsonReply(w,500,map[string]string{"error":"request creation failed"});return}
 req.Header.Set("Authorization","Apikey "+s.uploadKey);req.Header.Set("Content-Type",writer.FormDataContentType())
 resp,err:=s.client.Do(req)
 if err!=nil {s.mu.Lock();p.Status="unknown";p.ProviderResponse=err.Error();s.mu.Unlock();jsonReply(w,502,p);return}
 defer resp.Body.Close();data,_:=io.ReadAll(io.LimitReader(resp.Body,16000))
 s.mu.Lock();p.ProviderResponse=string(data);p.Status="unknown"
 if resp.StatusCode>=400 {p.Status="failed"}
 // Do not infer a published Facebook post from HTTP 200 alone.
 s.mu.Unlock();jsonReply(w,202,p)
}
func (s *server) getPost(w http.ResponseWriter,r *http.Request){
 if r.Method!=http.MethodGet {http.Error(w,"method not allowed",405);return}
 id:=strings.TrimPrefix(r.URL.Path,"/api/posts/")
 s.mu.Lock();p:=s.posts[id];if p==nil{s.mu.Unlock();http.NotFound(w,r);return};copy:=*p;s.mu.Unlock();jsonReply(w,200,copy)
}
func required(k string)string{v:=strings.TrimSpace(os.Getenv(k));if v==""{log.Fatalf("missing %s",k)};return v}
func main(){
 token:=required("BRIDGE_TOKEN");key:=required("UPLOAD_POST_API_KEY");base:=strings.TrimRight(required("PUBLIC_BASE_URL"),"/")
 if !strings.HasPrefix(base,"https://"){log.Fatal("PUBLIC_BASE_URL must use https")}
 dir:=os.Getenv("DATA_DIR");if dir==""{dir="./data"};if err:=os.MkdirAll(dir,0700);err!=nil{log.Fatal(err)}
 s:=&server{posts:make(map[string]*post),client:&http.Client{Timeout:95*time.Second},token:token,uploadKey:key,profile:"default",pageID:"1304976722709656",publicBase:base,dir:dir}
 mux:=http.NewServeMux()
 mux.HandleFunc("/healthz",func(w http.ResponseWriter,r *http.Request){fmt.Fprintln(w,"ok")})
 mux.HandleFunc("/media/",s.media)
 mux.HandleFunc("/api/assets",s.auth(s.upload))
 mux.HandleFunc("/api/posts/",s.auth(func(w http.ResponseWriter,r *http.Request){if r.Method=="GET"{s.getPost(w,r)}else{s.publish(w,r)}}))
 port:=os.Getenv("PORT");if port==""{port="8080"}
 log.Printf("bridge listening on :%s",port)
 if err:=http.ListenAndServe(":"+port,mux);!errors.Is(err,http.ErrServerClosed){log.Fatal(err)}
}
