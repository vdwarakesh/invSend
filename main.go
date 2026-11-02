package main

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"sync"
	"syscall"

	"go.mau.fi/whatsmeow"
	"go.mau.fi/whatsmeow/store/sqlstore"
	"go.mau.fi/whatsmeow/types"
	"go.mau.fi/whatsmeow/types/events"
	waLog "go.mau.fi/whatsmeow/util/log"

	waProto "go.mau.fi/whatsmeow/binary/proto" // adjust import path per your version
	"google.golang.org/protobuf/proto"

	_ "modernc.org/sqlite"
)

const port = "60995"

var client *whatsmeow.Client
var ctx = context.Background()

var qrMu sync.Mutex
var currentQR string

func setQR(code string) {
	qrMu.Lock()
	currentQR = code
	qrMu.Unlock()
}

func getQR() string {
	qrMu.Lock()
	defer qrMu.Unlock()
	return currentQR
}

func eventHandler(evt interface{}) {
	switch v := evt.(type) {
	case *events.Message:
		fmt.Println("Received a message!", v.Message.GetConversation())
	case *events.PairSuccess:
		setQR("") // clear QR once paired
	}
}

// --- HTTP handlers ---

func statusHandler(w http.ResponseWriter, r *http.Request) {
	loggedIn := client.Store.ID != nil
	resp := map[string]any{
		"logged_in": loggedIn,
		"connected": client.IsConnected(),
	}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(resp)
}

func qrHandler(w http.ResponseWriter, r *http.Request) {
	if client.Store.ID != nil {
		http.Error(w, `{"error":"already logged in"}`, http.StatusConflict)
		return
	}
	code := getQR()
	if code == "" {
		http.Error(w, `{"error":"qr not ready yet"}`, http.StatusNotFound)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"code": code})
}

type sendRequest struct {
	Number   string `json:"number"`
	Text     string `json:"text"`
	FileB64  string `json:"file_b64,omitempty"`
	FileName string `json:"file_name,omitempty"`
}

func sendHandler(w http.ResponseWriter, r *http.Request) {
	var req sendRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	jid := types.NewJID(req.Number, types.DefaultUserServer)

	var msg *waProto.Message

	if req.FileB64 != "" {
		data, err := base64.StdEncoding.DecodeString(req.FileB64)
		if err != nil {
			http.Error(w, "bad file_b64: "+err.Error(), http.StatusBadRequest)
			return
		}
		ext := strings.ToLower(filepath.Ext(req.FileName))
		isImage := ext == ".jpg" || ext == ".jpeg" || ext == ".png"

		mediaType := whatsmeow.MediaDocument
		if isImage {
			mediaType = whatsmeow.MediaImage
		}
		uploaded, err := client.Upload(ctx, data, mediaType)
		if err != nil {
			http.Error(w, "upload failed: "+err.Error(), http.StatusInternalServerError)
			return
		}

		if isImage {
			msg = &waProto.Message{
				ImageMessage: &waProto.ImageMessage{
					Caption:       proto.String(req.Text),
					Mimetype:      proto.String("image/" + strings.TrimPrefix(ext, ".")),
					URL:           proto.String(uploaded.URL),
					DirectPath:    proto.String(uploaded.DirectPath),
					MediaKey:      uploaded.MediaKey,
					FileEncSHA256: uploaded.FileEncSHA256,
					FileSHA256:    uploaded.FileSHA256,
					FileLength:    proto.Uint64(uint64(len(data))),
				},
			}
		} else {
			msg = &waProto.Message{
				DocumentMessage: &waProto.DocumentMessage{
					Title:         proto.String(req.FileName),
					FileName:      proto.String(req.FileName),
					Caption:       proto.String(req.Text),
					Mimetype:      proto.String("application/octet-stream"),
					URL:           proto.String(uploaded.URL),
					DirectPath:    proto.String(uploaded.DirectPath),
					MediaKey:      uploaded.MediaKey,
					FileEncSHA256: uploaded.FileEncSHA256,
					FileSHA256:    uploaded.FileSHA256,
					FileLength:    proto.Uint64(uint64(len(data))),
				},
			}
		}
	} else {
		msg = &waProto.Message{Conversation: proto.String(req.Text)}
	}

	_, err := client.SendMessage(ctx, jid, msg)
	if err != nil {
		http.Error(w, "send failed: "+err.Error(), http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.Write([]byte(`{"status":"ok"}`))
}

func main() {
	dbLog := waLog.Stdout("Database", "DEBUG", true)
	container, err := sqlstore.New(ctx, "sqlite", "file:invsend.db?_pragma=foreign_keys(1)", dbLog)
	if err != nil {
		panic(err)
	}
	deviceStore, err := container.GetFirstDevice(ctx)
	if err != nil {
		panic(err)
	}
	clientLog := waLog.Stdout("Client", "DEBUG", true)
	client = whatsmeow.NewClient(deviceStore, clientLog)
	client.AddEventHandler(eventHandler)

	if client.Store.ID == nil {
		qrChan, _ := client.GetQRChannel(ctx)
		if err = client.Connect(); err != nil {
			panic(err)
		}
		go func() {
			for evt := range qrChan {
				if evt.Event == "code" {
					setQR(evt.Code)
				} else {
					fmt.Println("Login event:", evt.Event)
					if evt.Event == "success" {
						setQR("")
					}
				}
			}
		}()
	} else {
		if err = client.Connect(); err != nil {
			panic(err)
		}
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/status", statusHandler)
	mux.HandleFunc("/qr", qrHandler)
	mux.HandleFunc("/send", sendHandler)

	go func() {
		fmt.Println("HTTP API listening on 127.0.0.1:" + port)
		http.ListenAndServe("127.0.0.1:"+port, mux)
	}()

	c := make(chan os.Signal, 1)
	signal.Notify(c, os.Interrupt, syscall.SIGTERM)
	<-c
	client.Disconnect()
}
