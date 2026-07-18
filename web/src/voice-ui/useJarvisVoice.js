import { useCallback, useEffect, useRef, useState } from "react";

const MIN_SPEECH_THRESHOLD = 0.01;
const SPEECH_ONSET_FRAMES = 5;
const END_SILENCE_MS = 1800;
const MIN_SPEECH_MS = 120;
const CONTAINER_TAG = "hackathon-user";

function wsUrl(path) {
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${location.host}${path}`;
}

function blobToBase64(blob) {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve(reader.result.split(",")[1]);
    reader.readAsDataURL(blob);
  });
}

export function useJarvisVoice() {
  const [inputText, setInputText] = useState("");
  const [answerText, setAnswerText] = useState("");
  const [statusText, setStatusText] = useState("Connecting…");
  const [metricsText, setMetricsText] = useState("");
  const [sending, setSending] = useState(true);
  const [listening, setListening] = useState(false);
  const [muted, setMuted] = useState(false);
  const [pushToTalkActive, setPushToTalkActive] = useState(false);
  const [micState, setMicState] = useState("Mic off");
  const [level, setLevel] = useState(0);

  const socketRef = useRef(null);
  const listenSocketRef = useRef(null);
  const sessionIdRef = useRef(
    localStorage.getItem("jarvisSessionId") || crypto.randomUUID()
  );
  const inputRef = useRef("");
  const sendingRef = useRef(true);
  const pendingTranscriptRef = useRef("");
  const lastTranscriptRef = useRef({ text: "", at: 0 });

  const audioQueueRef = useRef([]);
  const playingRef = useRef(false);
  const currentAudioRef = useRef(null);

  const micStreamRef = useRef(null);
  const audioContextRef = useRef(null);
  const analyserRef = useRef(null);
  const utteranceRecorderRef = useRef(null);
  const utteranceChunksRef = useRef([]);
  const listeningRef = useRef(false);
  const mutedRef = useRef(false);
  const speechActiveRef = useRef(false);
  const speechStartedAtRef = useRef(0);
  const silenceStartedAtRef = useRef(0);
  const noiseFloorRef = useRef(0.003);
  const speechOnsetFramesRef = useRef(0);
  const pushToTalkRef = useRef(false);
  const rafRef = useRef(null);

  useEffect(() => {
    localStorage.setItem("jarvisSessionId", sessionIdRef.current);
  }, []);

  useEffect(() => {
    inputRef.current = inputText;
  }, [inputText]);

  const stopSpeechPlayback = useCallback(() => {
    audioQueueRef.current = [];
    if (currentAudioRef.current) {
      currentAudioRef.current.pause();
      currentAudioRef.current = null;
    }
    playingRef.current = false;
  }, []);

  const playNext = useCallback(() => {
    if (playingRef.current || !audioQueueRef.current.length) return;
    playingRef.current = true;
    const item = audioQueueRef.current.shift();
    const audio = new Audio(`data:audio/wav;base64,${item.wav}`);
    currentAudioRef.current = audio;
    setMetricsText(
      `first audio ${item.readySeconds.toFixed(1)}s · ${item.duration.toFixed(1)}s voice`
    );
    const finish = () => {
      playingRef.current = false;
      currentAudioRef.current = null;
      playNext();
    };
    audio.onended = finish;
    audio.onerror = finish;
    audio.play();
  }, []);

  const ask = useCallback((rawText) => {
    const text = (rawText ?? inputRef.current).trim();
    if (!text || socketRef.current?.readyState !== WebSocket.OPEN) return;
    setAnswerText("");
    setStatusText("Starting…");
    setMetricsText("");
    setSending(true);
    sendingRef.current = true;
    setInputText("");
    socketRef.current.send(
      JSON.stringify({
        type: "query",
        text,
        containerTag: CONTAINER_TAG,
        sessionId: sessionIdRef.current,
      })
    );
  }, []);

  useEffect(() => {
    let cancelled = false;
    let reconnectTimer = null;

    function connect() {
      if (cancelled) return;
      const socket = new WebSocket(wsUrl("/ws"));
      socketRef.current = socket;
      socket.onopen = () => {
        setStatusText("Ready");
        setSending(false);
        sendingRef.current = false;
      };
      socket.onclose = () => {
        setStatusText("Reconnecting…");
        setSending(true);
        sendingRef.current = true;
        reconnectTimer = setTimeout(connect, 1000);
      };
      socket.onmessage = (event) => {
        const message = JSON.parse(event.data);
        if (message.type === "token") {
          setAnswerText((prev) => prev + message.text);
        }
        if (message.type === "status" || message.type === "warning") {
          setStatusText(message.message);
        }
        if (message.type === "memory") {
          setStatusText(
            `${message.count} memories · ${Math.round(message.latency * 1000)}ms`
          );
        }
        if (message.type === "metric" && message.name === "firstToken") {
          setMetricsText(`first token ${message.seconds.toFixed(2)}s`);
        }
        if (message.type === "audio") {
          audioQueueRef.current.push(message);
          playNext();
        }
        if (message.type === "done") {
          setStatusText(`Done · ${message.seconds.toFixed(1)}s`);
          setSending(false);
          sendingRef.current = false;
          if (pendingTranscriptRef.current) {
            const next = pendingTranscriptRef.current;
            pendingTranscriptRef.current = "";
            ask(next);
          }
        }
        if (message.type === "error") {
          setStatusText(message.message);
          setSending(false);
          sendingRef.current = false;
        }
      };
    }

    connect();
    return () => {
      cancelled = true;
      clearTimeout(reconnectTimer);
      socketRef.current?.close();
    };
  }, [ask, playNext]);

  const submitUtterance = useCallback(async (chunks, mimeType) => {
    const blob = new Blob(chunks, { type: mimeType });
    if (blob.size < 400 || listenSocketRef.current?.readyState !== WebSocket.OPEN) {
      return;
    }
    setMicState("Transcribing…");
    const audio = await blobToBase64(blob);
    listenSocketRef.current.send(JSON.stringify({ type: "transcribe", audio, mimeType }));
  }, []);

  const beginUtteranceRecording = useCallback(() => {
    const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : "audio/webm";
    utteranceChunksRef.current = [];
    const recorder = new MediaRecorder(micStreamRef.current, { mimeType });
    recorder.ondataavailable = (event) => {
      if (event.data.size) utteranceChunksRef.current.push(event.data);
    };
    recorder.start();
    utteranceRecorderRef.current = recorder;
  }, []);

  const endUtteranceRecording = useCallback(
    (shouldSubmit) => {
      const recorder = utteranceRecorderRef.current;
      if (!recorder || recorder.state === "inactive") return;
      const mimeType = recorder.mimeType;
      recorder.onstop = () => {
        const chunks = utteranceChunksRef.current;
        utteranceChunksRef.current = [];
        if (shouldSubmit) submitUtterance(chunks, mimeType);
      };
      recorder.stop();
      utteranceRecorderRef.current = null;
    },
    [submitUtterance]
  );

  const monitorMic = useCallback(() => {
    if (!listeningRef.current) return;
    const analyser = analyserRef.current;
    const samples = new Float32Array(analyser.fftSize);
    analyser.getFloatTimeDomainData(samples);
    let energy = 0;
    for (const sample of samples) energy += sample * sample;
    const rms = Math.sqrt(energy / samples.length);
    setLevel(Math.min(1, rms * 14));
    const now = performance.now();
    if (pushToTalkRef.current) {
      rafRef.current = requestAnimationFrame(monitorMic);
      return;
    }
    // Calibrate against the room continuously while nobody is speaking. This
    // keeps short, softly spoken commands from being rejected by a fixed gate.
    if (!speechActiveRef.current && !mutedRef.current) {
      noiseFloorRef.current = noiseFloorRef.current * 0.97 + rms * 0.03;
    }
    const speechThreshold = Math.max(
      MIN_SPEECH_THRESHOLD,
      noiseFloorRef.current * 2.1
    );

    if (!mutedRef.current && rms > speechThreshold) {
      speechOnsetFramesRef.current += 1;
      silenceStartedAtRef.current = 0;
      if (!speechActiveRef.current && speechOnsetFramesRef.current >= SPEECH_ONSET_FRAMES) {
        speechActiveRef.current = true;
        speechStartedAtRef.current = now;
        beginUtteranceRecording();
        setMicState("Listening…");
        stopSpeechPlayback();
      }
    } else if (speechActiveRef.current) {
      speechOnsetFramesRef.current = 0;
      if (!silenceStartedAtRef.current) silenceStartedAtRef.current = now;
      if (now - silenceStartedAtRef.current >= END_SILENCE_MS) {
        speechActiveRef.current = false;
        const duration = now - speechStartedAtRef.current;
        endUtteranceRecording(duration >= MIN_SPEECH_MS);
        if (duration < MIN_SPEECH_MS) {
          setMicState(mutedRef.current ? "Muted" : "Always listening");
        }
      }
    } else {
      speechOnsetFramesRef.current = 0;
    }
    rafRef.current = requestAnimationFrame(monitorMic);
  }, [beginUtteranceRecording, endUtteranceRecording, stopSpeechPlayback]);

  const connectListener = useCallback(() => {
    const socket = new WebSocket(wsUrl("/listen"));
    listenSocketRef.current = socket;
    socket.onclose = () => {
      if (listeningRef.current) setTimeout(connectListener, 1000);
    };
    socket.onmessage = (event) => {
      const message = JSON.parse(event.data);
      if (message.type === "transcript") {
        setMicState(`Heard in ${message.seconds.toFixed(2)}s`);
        const text = (message.text || "").trim();
        if (!text) {
          setMicState(mutedRef.current ? "Muted" : "Didn't hear anything");
          return;
        }
        const normalized = text.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
        const duplicate = normalized === lastTranscriptRef.current.text
          && Date.now() - lastTranscriptRef.current.at < 30000;
        if (duplicate) {
          setMicState("Ignored repeated transcript");
          return;
        }
        lastTranscriptRef.current = { text: normalized, at: Date.now() };
        setInputText(text);
        if (sendingRef.current) {
          pendingTranscriptRef.current = text;
        } else {
          ask(text);
        }
      }
      if (message.type === "transcription_error") {
        setMicState(`STT error: ${message.message}`);
      }
    };
  }, [ask]);

  const startListening = useCallback(async () => {
    micStreamRef.current = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        channelCount: 1,
        sampleRate: 48000,
      },
    });
    const audioContext = new AudioContext();
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 1024;
    audioContext.createMediaStreamSource(micStreamRef.current).connect(analyser);
    audioContextRef.current = audioContext;
    analyserRef.current = analyser;
    listeningRef.current = true;
    setListening(true);
    setMicState("Always listening");
    connectListener();
    monitorMic();
  }, [connectListener, monitorMic]);

  const toggleMute = useCallback(() => {
    mutedRef.current = !mutedRef.current;
    setMuted(mutedRef.current);
    setMicState(mutedRef.current ? "Muted" : "Always listening");
  }, []);

  const togglePushToTalk = useCallback(() => {
    if (!listeningRef.current || mutedRef.current) return;
    if (pushToTalkRef.current) {
      pushToTalkRef.current = false;
      setPushToTalkActive(false);
      endUtteranceRecording(true);
      setMicState("Transcribing…");
      return;
    }
    const alreadyRecording = speechActiveRef.current;
    speechActiveRef.current = false;
    pushToTalkRef.current = true;
    setPushToTalkActive(true);
    if (!alreadyRecording) beginUtteranceRecording();
    stopSpeechPlayback();
    setMicState("Push to talk · tap again when done");
  }, [beginUtteranceRecording, endUtteranceRecording, stopSpeechPlayback]);

  useEffect(() => {
    return () => {
      cancelAnimationFrame(rafRef.current);
      listenSocketRef.current?.close();
      micStreamRef.current?.getTracks().forEach((track) => track.stop());
      audioContextRef.current?.close();
    };
  }, []);

  return {
    inputText,
    setInputText,
    answerText,
    statusText,
    metricsText,
    sending,
    ask,
    listening,
    muted,
    pushToTalkActive,
    micState,
    level,
    startListening,
    toggleMute,
    togglePushToTalk,
  };
}
