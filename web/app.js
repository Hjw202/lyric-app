/**
 * 歌词显示客户端 - WebSocket + 逐行高亮渲染
 *
 * WebSocket 协议:
 *   {"type":"song",   "title":"...", "artist":"..."}   — 曲目变更
 *   {"type":"lyrics", "lines":["行1","行2",...]}       — 完整歌词列表
 *   {"type":"line",   "index":5}                        — 当前行索引
 *   {"type":"style",  "data":{...}}                     — 样式更新
 *   {"type":"ping"}                                      — 心跳
 */

class LyricClient {
    constructor() {
        this.ws = null;
        this.reconnectDelay = 2000;
        this.maxReconnectDelay = 30000;
        this.lyricsEl = document.getElementById('lyrics');
        this.statusEl = document.getElementById('status');
        this.songEl = document.getElementById('song-title');
        this.lineEls = [];      // 所有歌词行 DOM 元素
        this.currentIndex = -1;  // 当前行索引
        this.styleDefaults = {
            color: [0, 255, 0],
            bg_color: [0, 0, 0],
            font_size: 48,
            line_spacing: 10,
            padding: 40,
            char_interval: 200,
        };
    }

    // ---- WebSocket 连接 ----

    connect() {
        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url = `${protocol}//${location.host}/ws`;
        this.ws = new WebSocket(url);
        this.ws.onopen = () => this.onOpen();
        this.ws.onmessage = (e) => this.onMessage(e);
        this.ws.onclose = () => this.onClose();
        this.ws.onerror = () => {};
    }

    onOpen() {
        this.reconnectDelay = 2000;
        this.statusEl.classList.add('hidden');
    }

    onClose() {
        this.showStatus('正在重连');
        setTimeout(() => {
            this.reconnectDelay = Math.min(this.reconnectDelay * 1.5, this.maxReconnectDelay);
            this.connect();
        }, this.reconnectDelay);
    }

    onMessage(event) {
        let msg;
        try {
            msg = JSON.parse(event.data);
        } catch {
            return;
        }
        switch (msg.type) {
            case 'song':
                this.renderSong(msg.title, msg.artist);
                break;
            case 'lyrics':
                this.renderLyrics(msg.lines || []);
                break;
            case 'line':
                this.highlightLine(msg.index);
                break;
            case 'style':
                this.applyStyle(msg.data);
                break;
            case 'ping':
                this.ws.send(JSON.stringify({ type: 'pong' }));
                break;
        }
    }

    // ---- 歌词渲染 ----

    renderSong(title, artist) {
        const text = artist ? `${title} - ${artist}` : title;
        this.songEl.textContent = text;
        this.songEl.classList.remove('hidden');
    }

    renderLyrics(lines) {
        this.lyricsEl.innerHTML = '';
        this.lineEls = [];
        this.currentIndex = -1;

        if (!lines || lines.length === 0) {
            const empty = document.createElement('div');
            empty.className = 'lyric-empty';
            empty.textContent = '暂无歌词';
            this.lyricsEl.appendChild(empty);
            return;
        }

        for (const text of lines) {
            const el = document.createElement('div');
            el.className = 'lyric-line';
            el.textContent = text;
            this.lyricsEl.appendChild(el);
            this.lineEls.push(el);
        }
    }

    highlightLine(index) {
        if (index === this.currentIndex) return;
        const old = this.currentIndex;
        this.currentIndex = index;

        // 更新所有行样式
        this.lineEls.forEach((el, i) => {
            el.classList.remove('current', 'prev', 'next', 'near');
            if (i === index) {
                el.classList.add('current');
            } else if (i === index - 1) {
                el.classList.add('prev');
            } else if (i === index + 1) {
                el.classList.add('next');
            } else if (Math.abs(i - index) <= 2) {
                el.classList.add('near');
            }
        });

        // 滚动当前行到视图中心
        if (index >= 0 && index < this.lineEls.length) {
            const el = this.lineEls[index];
            el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    }

    // ---- 样式应用 ----

    applyStyle(data) {
        const merged = { ...this.styleDefaults, ...data };

        if (merged.color) {
            const c = merged.color;
            const rgb = `rgb(${c[0]}, ${c[1]}, ${c[2]})`;
            const rgba = `rgba(${c[0]}, ${c[1]}, ${c[2]}, 0.35)`;
            document.documentElement.style.setProperty('--text-color', rgb);
            document.documentElement.style.setProperty('--text-dim-color', rgba);
        }

        if (merged.bg_color) {
            const c = merged.bg_color;
            document.documentElement.style.setProperty('--bg-color', `rgb(${c[0]}, ${c[1]}, ${c[2]})`);
        }

        if (merged.font_size) {
            document.documentElement.style.setProperty('--font-size', `${merged.font_size}px`);
        }

        if (merged.line_spacing) {
            document.documentElement.style.setProperty('--line-spacing', `${merged.line_spacing}px`);
        }

        if (merged.padding) {
            document.documentElement.style.setProperty('--padding', `${merged.padding}px`);
        }
    }

    // ---- UI 辅助 ----

    showStatus(text) {
        this.statusEl.querySelector('.status-text').textContent = text;
        this.statusEl.classList.remove('hidden');
    }
}

// 启动
const client = new LyricClient();
client.applyStyle({});
client.connect();
