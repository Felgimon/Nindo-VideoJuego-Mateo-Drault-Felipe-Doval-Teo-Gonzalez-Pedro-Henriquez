// Aviso de ataque (ensō): una pincelada de tinta que rodea al atacante y se cierra EXACTO cuando hay que
// apretar (Enemy.TellProgress01). La dibuja FX/CombatTelegraphs en un quad horizontal (v = hacia donde
// arranca el trazo: el costado en pantalla que da a Kaito; el quad se espeja para que gire primero por detrás).
//  _Mode 0  ensō: trazo de pincel en sentido horario visto desde arriba (en el quad), entra fino, engorda y afina en la
//           punta, con pelos secos al final. Debajo, un halo de tinta oscura (se lee sobre nieve, agua y
//           antorchas). El ancho nunca baja de _MinPx píxeles de pantalla (fwidth), a cualquier distancia.
//           Dorado = parry al cerrarse; rojo dentado = imparable, dash al cerrarse.
//  _Mode 1  disco de la zona real que golpea (pisotón, giro), se llena desde el centro al ritmo del anillo.
//  _Mode 2  carril (embestida, tajo a distancia), se llena desde el atacante.
// _Outcome: 1 desviado (el anillo se parte en 8 y sale volando), 2 cortado (la tinta se deshace), 3 golpe (se apaga).
// Una sola pasada, alfa premultiplicado: la tinta oscurece el suelo y el trazo lo cubre con color HDR (bloom). Sin texto ni kanji.
Shader "Nindo/Telegraph"
{
    Properties
    {
        _Color ("Color", Color) = (1, 0.84, 0.47, 1)
        _HotColor ("Color al cerrarse", Color) = (1, 0.9, 0.55, 1)
        _Mode ("0 ensō, 1 disco, 2 carril", Float) = 0
        _Progress ("Progreso del trazo / relleno", Range(0, 1)) = 0
        _Hot ("Tramo caliente (más claro)", Range(0, 1)) = 0
        _Flash ("Destello al cerrarse", Range(0, 1)) = 0
        _Danger ("Imparable", Range(0, 1)) = 0
        _Alpha ("Opacidad", Range(0, 1)) = 1
        _Radius ("Radio del anillo / borde (0..1 del quad)", Float) = 0.6
        _Width ("Medio ancho del trazo / fin del carril (0..1)", Float) = 0.05
        _Dot ("Radio del punto de la punta (0..1)", Float) = 0.06
        _MinPx ("Ancho mínimo en píxeles", Float) = 12
        _Outcome ("0 dibujando, 1 desviado, 2 cortado, 3 golpe", Float) = 0
        _OutT ("Avance del final (0..1)", Range(0, 1)) = 0
        _Seed ("Semilla del pincel", Float) = 0
        _Ink ("Tinta", Color) = (0.07, 0.04, 0.047, 1)
    }

    SubShader
    {
        Tags { "RenderType" = "Transparent" "Queue" = "Transparent-10" "RenderPipeline" = "UniversalPipeline" "IgnoreProjector" = "True" }
        Blend One OneMinusSrcAlpha
        ZWrite Off
        ZTest LEqual
        Offset -2, -2
        Cull Off

        Pass
        {
            Name "Telegraph"
            Tags { "LightMode" = "UniversalForward" }
            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_instancing
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

            CBUFFER_START(UnityPerMaterial)
                half4 _Color, _HotColor, _Ink;
                float _Mode, _Progress, _Hot, _Flash, _Danger, _Alpha, _Radius, _Width, _Dot, _MinPx, _Outcome, _OutT, _Seed;
            CBUFFER_END

            struct A { float4 pos : POSITION; float2 uv : TEXCOORD0; UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct V { float4 pos : SV_POSITION; float2 p : TEXCOORD0; UNITY_VERTEX_OUTPUT_STEREO };

            V vert(A i)
            {
                V o;
                UNITY_SETUP_INSTANCE_ID(i);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.pos = TransformObjectToHClip(i.pos.xyz);
                o.p = i.uv * 2 - 1;   // -1..1: x = derecha, y = adelante (inicio del trazo)
                return o;
            }

            float hash(float2 p) { return frac(sin(dot(p, float2(127.1, 311.7))) * 43758.5453); }
            float vnoise(float2 p)
            {
                float2 i = floor(p), f = frac(p), u = f * f * (3 - 2 * f);
                return lerp(lerp(hash(i), hash(i + float2(1, 0)), u.x), lerp(hash(i + float2(0, 1)), hash(i + float2(1, 1)), u.x), u.y);
            }
            float band(float d, float w, float px) { return 1 - smoothstep(w - px, w + px, d); }

            // final: 1 desviado (se apaga rápido), 2 cortado (se deshace), 3 golpe (se apaga)
            float OutcomeFade(float2 p)
            {
                if (_Outcome < 0.5) return 1;
                if (_Outcome < 1.5) return pow(1 - _OutT, 1.5);
                if (_Outcome < 2.5) return step(_OutT, vnoise(p * 7 + _Seed) * 0.95 + 0.04);
                return 1 - _OutT;
            }

            // px: tamaño de un píxel en unidades del quad (las derivadas se toman en frag, fuera de los if)
            half4 Enso(float2 p, float d, float px)
            {
                float s = frac(atan2(p.x, p.y) * 0.15915494 + 1.0);   // 0..1 a lo largo de la vuelta, horario desde arriba
                float f = saturate(_Progress);
                float closed = smoothstep(0.985, 1.0, f);
                float shatter = (_Outcome > 0.5 && _Outcome < 1.5) ? _OutT : 0;

                float r = _Radius * (1 + 0.012 * sin(s * 18.85 + _Seed)) * (1 + 0.55 * shatter);
                // ancho: presión del pincel y borde áspero; nunca menos de _MinPx px en pantalla DESPUÉS de modularlo
                // (antes el mínimo se aplicaba antes y el último cuarto, el que se mira para apretar, quedaba en ~9 px)
                float w0 = max(_Width, _MinPx * 0.5 * px);
                float pressure = (0.72 + 0.38 * sin(3.14159 * s)) * smoothstep(0.0, 0.06, s);
                float tip = lerp(saturate((f - s) * 6.2832 * _Radius / (w0 * 3.0)), 1.0, closed);
                float w = max(w0 * pressure * (0.9 + 0.2 * vnoise(float2(s * 90, _Seed))), _MinPx * 0.5 * px) * sqrt(tip);
                w *= 1 + _Danger * 0.6 * step(0.5, frac(s * 12 + 0.25));    // dientes del imparable
                w *= 1 + 0.8 * _Flash;

                float drawn = step(s, f);
                float seg = frac(s * 8 + _Seed);                                // pedazos al desviarlo
                drawn *= shatter > 0 ? step(0.06 + 0.3 * shatter, seg) * step(seg, 0.97 - 0.1 * shatter) : 1;
                float dist = abs(d - r);

                // pincel seco: rayas de pelo que se abren hacia el final del trazo (sutiles: ese tramo es el que avisa)
                float v = (d - r) / max(w, 1e-4);
                float hair = vnoise(float2(v * 6 + _Seed * 3, s * 4));
                float dry = 0.08 + 0.17 * smoothstep(0.5, 1.0, s);
                float stroke = band(dist, w, px) * drawn * (1 - 0.85 * step(hair, dry) * (1 - _Flash));
                float ink = band(dist, w * 1.6 + 1.5 * px, px) * drawn;

                // punto brillante en la punta mientras se dibuja
                float2 hp = r * float2(sin(f * 6.2832), cos(f * 6.2832));
                float dotA = band(length(p - hp), max(_Dot, 3 * px), px) * (1 - closed) * step(_Outcome, 0.5) * step(0.001, f);

                float fade = _Alpha * OutcomeFade(p);
                stroke *= fade; ink *= fade * 0.55; dotA *= fade;
                half3 col = lerp(_Color.rgb, _HotColor.rgb, saturate(_Hot + shatter));
                if (_Outcome > 1.5 && _Outcome < 2.5) col = lerp(col, _Ink.rgb, _OutT);
                col *= 1.15 + 1.6 * _Flash;                                    // HDR: el bloom lo hace brillar
                float under = ink * (1 - stroke);
                half3 rgb = _Ink.rgb * under + col * stroke + _HotColor.rgb * 2.0 * dotA;
                // el trazo tapa casi todo el fondo: sobre nieve o agua clara sigue viéndose dorado/rojo, no blanco
                return half4(rgb, under + stroke * 0.8 + dotA * 0.2);
            }

            half4 Disc(float2 p, float d, float px)
            {
                float teeth = 1 - _Danger * 0.03 * step(0.5, frac(atan2(p.x, p.y) * 0.15915494 * 24));
                float re = _Radius * teeth;
                float f = saturate(_Progress);
                float inside = band(d, re, px);
                float fill = band(d, re * f, px) * inside * (0.18 + 0.17 * f) * (0.85 + 0.15 * sin(d * 30 - _Time.y * 8));
                float edge = band(abs(d - re), 1.5 * px + 0.006, px);
                float ink = band(abs(d - re), 4 * px + 0.012, px);
                float fade = _Alpha * OutcomeFade(p);
                fill *= fade; edge *= fade * (0.5 + 0.4 * f); ink *= fade * 0.5;
                half3 col = _Color.rgb * 1.3;
                float under = ink * (1 - edge);
                return half4(_Ink.rgb * under + col * (edge + fill), under + edge * 0.4 + fill * 0.6);
            }

            half4 Lane(float2 p, float pxx, float pxy)
            {
                float ex = _Radius * (1 - _Danger * 0.05 * step(0.5, frac(p.y * 6)));   // borde lateral dentado
                float ey = _Width;                                                       // fin del carril
                float ax = abs(p.x);
                float f = saturate(_Progress);
                float inX = band(ax, ex, pxx), inY = band(p.y, ey, pxy);
                float fill = inX * inY * band(p.y, lerp(-1, ey, f), pxy) * (0.18 + 0.17 * f) * (0.85 + 0.15 * sin(p.y * 20 - _Time.y * 8));
                float edge = max(band(abs(ax - ex), 1.5 * pxx, pxx) * inY, band(abs(p.y - ey), 1.5 * pxy, pxy) * inX);
                float ink = max(band(abs(ax - ex), 4 * pxx, pxx) * inY, band(abs(p.y - ey), 4 * pxy, pxy) * inX);
                float fade = _Alpha * OutcomeFade(p);
                fill *= fade; edge *= fade * (0.5 + 0.4 * f); ink *= fade * 0.5;
                half3 col = _Color.rgb * 1.3;
                float under = ink * (1 - edge);
                return half4(_Ink.rgb * under + col * (edge + fill), under + edge * 0.4 + fill * 0.6);
            }

            half4 frag(V i) : SV_Target
            {
                float d = length(i.p);
                float px = max(fwidth(d), 1e-5);
                float pxx = max(fwidth(i.p.x), 1e-5), pxy = max(fwidth(i.p.y), 1e-5);
                if (_Mode < 0.5) return Enso(i.p, d, px);
                if (_Mode < 1.5) return Disc(i.p, d, px);
                return Lane(i.p, pxx, pxy);
            }
            ENDHLSL
        }
    }
}
