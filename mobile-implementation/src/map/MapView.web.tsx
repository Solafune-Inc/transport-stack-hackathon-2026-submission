import { useEffect, useImperativeHandle, useMemo, useRef, useState, type Ref } from 'react';
import type { Levels, MapCommand, MapMessage, MapState } from '../types';
import { MAP_HTML } from './mapHtml.generated';

export interface MapHandle {
  send(cmd: MapCommand): void;
}

interface Props {
  levels: Levels;
  initial: MapState;
  onMessage(msg: MapMessage): void;
  ref?: Ref<MapHandle>;
}

type MapWindow = Window & { __app?: { cmd(c: MapCommand): void } };

/** Web build: the same map page in a same-origin iframe instead of a native WebView. */
export function MapView({ levels, initial, onMessage, ref }: Props) {
  const frame = useRef<HTMLIFrameElement>(null);
  const ready = useRef(false);
  const queue = useRef<MapCommand[]>([]);
  const onMessageRef = useRef(onMessage);
  const [initialState] = useState(initial);

  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  const html = useMemo(() => {
    const boot = JSON.stringify({ levels, state: initialState }).replace(/</g, '\\u003c');
    // the map page posts through window.ReactNativeWebView; bridge it to the parent window
    const bridge = '<script>window.ReactNativeWebView={postMessage:function(s){parent.postMessage({busMap:s},"*")}};</script>';
    return MAP_HTML.replace('/*__BOOT_JSON__*/null', () => boot).replace(
      '<div id="map"></div>',
      () => `<div id="map"></div>${bridge}`,
    );
  }, [levels, initialState]);

  useImperativeHandle(ref, () => {
    const inject = (cmd: MapCommand) => (frame.current?.contentWindow as MapWindow | null)?.__app?.cmd(cmd);
    return {
      send(cmd: MapCommand) {
        if (ready.current) inject(cmd);
        else queue.current.push(cmd);
      },
    };
  });

  useEffect(() => {
    const inject = (cmd: MapCommand) => (frame.current?.contentWindow as MapWindow | null)?.__app?.cmd(cmd);
    const listener = (e: MessageEvent) => {
      if (e.source !== frame.current?.contentWindow || typeof e.data?.busMap !== 'string') return;
      const msg = JSON.parse(e.data.busMap) as MapMessage;
      if (msg.type === 'ready') {
        ready.current = true;
        queue.current.forEach(inject);
        queue.current = [];
      }
      onMessageRef.current(msg);
    };
    window.addEventListener('message', listener);
    return () => window.removeEventListener('message', listener);
  }, []);

  return (
    <iframe
      ref={frame}
      srcDoc={html}
      title="Bus map"
      style={{ border: 'none', flex: 1, width: '100%', height: '100%', backgroundColor: '#e8eaed' }}
    />
  );
}
