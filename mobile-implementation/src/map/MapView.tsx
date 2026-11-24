import { useImperativeHandle, useMemo, useRef, useState, type Ref } from 'react';
import { Linking, StyleSheet } from 'react-native';
import { WebView, type WebViewMessageEvent } from 'react-native-webview';
import type { Levels, MapCommand, MapMessage, MapState } from '../types';
import { MAP_HTML } from './mapHtml.generated';

// react-native-webview defaults its props generic to `undefined`, which TS 6 intersects to `never`.
const TypedWebView = WebView<object>;
type WebViewRef = WebView<object>;

export interface MapHandle {
  send(cmd: MapCommand): void;
}

interface Props {
  levels: Levels;
  /** state at first render only; later changes go through `send` */
  initial: MapState;
  onMessage(msg: MapMessage): void;
  ref?: Ref<MapHandle>;
}

export function MapView({ levels, initial, onMessage, ref }: Props) {
  const web = useRef<WebViewRef>(null);
  const ready = useRef(false);
  const queue = useRef<MapCommand[]>([]);
  const [initialState] = useState(initial);

  const html = useMemo(() => {
    const boot = JSON.stringify({ levels, state: initialState }).replace(/</g, '\\u003c');
    return MAP_HTML.replace('/*__BOOT_JSON__*/null', () => boot);
  }, [levels, initialState]);

  const inject = (cmd: MapCommand) =>
    web.current?.injectJavaScript(`window.__app&&window.__app.cmd(${JSON.stringify(cmd)});true;`);

  useImperativeHandle(ref, () => ({
    send(cmd: MapCommand) {
      if (ready.current) inject(cmd);
      else queue.current.push(cmd);
    },
  }));

  const handleMessage = (e: WebViewMessageEvent) => {
    let msg: MapMessage;
    try {
      msg = JSON.parse(e.nativeEvent.data) as MapMessage;
    } catch {
      return;
    }
    if (msg.type === 'ready') {
      ready.current = true;
      queue.current.forEach(inject);
      queue.current = [];
    }
    onMessage(msg);
  };

  return (
    <TypedWebView
      ref={web}
      style={styles.map}
      originWhitelist={['*']}
      source={{ html }}
      onMessage={handleMessage}
      javaScriptEnabled
      domStorageEnabled
      setSupportMultipleWindows={false}
      // attribution links open in the system browser instead of replacing the map page
      onShouldStartLoadWithRequest={(req) => {
        if (!req.url.startsWith('http')) return true;
        Linking.openURL(req.url);
        return false;
      }}
      onOpenWindow={(e) => Linking.openURL(e.nativeEvent.targetUrl)}
      onContentProcessDidTerminate={() => {
        ready.current = false;
        web.current?.reload();
      }}
    />
  );
}

const styles = StyleSheet.create({
  map: { flex: 1, backgroundColor: '#e8eaed' },
});
