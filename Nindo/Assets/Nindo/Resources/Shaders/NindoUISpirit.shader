// HUD de Nindō: el dragón dorado del Espíritu de la Bandana, vivo.
//  * nada: todo el cuerpo ondula como si nadara (la fase sale de la posición en el canvas, así el
//    marco y el relleno ondulan juntos aunque sean dos imágenes);
//  * el relleno es oro líquido: borde que tiembla y brilla, escamas que destellan y un reflejo que
//    recorre el cuerpo de la cola a la cabeza; al gastar queda una estela clara que se vacía;
//  * Filo de Ira: el calor acumulado entra rojo desde la cabeza; activo, el dragón arde (tinte
//    carmesí que parpadea y un aura de fuego que sube del cuerpo).
// _Mode: 0 = marco (silueta oscura), 1 = relleno. El tiempo llega sin escala desde UIManager (_T),
// así sigue vivo en pausa y en cámara lenta. Basado en UI/Default (stencil, máscaras, clip rect).
Shader "Nindo/UI Spirit"
{
    Properties
    {
        [PerRendererData] _MainTex ("Sprite", 2D) = "white" {}
        _Color ("Tinte", Color) = (1, 1, 1, 1)
        _Mode ("0 marco / 1 relleno", Float) = 1
        _Fill ("Relleno", Range(0, 1)) = 1
        _Ghost ("Estela al gastar", Range(0, 1)) = 0
        _WaveAmp ("Ondulación (uv)", Float) = 0.03
        _WaveFreq ("Frecuencia (por unidad de canvas)", Float) = 0.012
        _WaveSpeed ("Velocidad de la ondulación", Float) = 1.8
        _Shine ("Brillo de escamas", Range(0, 1)) = 0.7
        _Heat ("Ira acumulada", Range(0, 1)) = 0
        _Rage ("Filo de Ira activo", Range(0, 1)) = 0
        _Pulse ("Pulso (ganó espíritu)", Range(0, 1)) = 0
        _Deny ("No alcanza el espíritu", Range(0, 1)) = 0
        _T ("Tiempo sin escala", Float) = 0

        _StencilComp ("Stencil Comparison", Float) = 8
        _Stencil ("Stencil ID", Float) = 0
        _StencilOp ("Stencil Operation", Float) = 0
        _StencilWriteMask ("Stencil Write Mask", Float) = 255
        _StencilReadMask ("Stencil Read Mask", Float) = 255
        _ColorMask ("Color Mask", Float) = 15
        [Toggle(UNITY_UI_ALPHACLIP)] _UseUIAlphaClip ("Use Alpha Clip", Float) = 0
    }

    SubShader
    {
        Tags { "Queue" = "Transparent" "IgnoreProjector" = "True" "RenderType" = "Transparent" "PreviewType" = "Plane" "CanUseSpriteAtlas" = "True" }
        Stencil
        {
            Ref [_Stencil]
            Comp [_StencilComp]
            Pass [_StencilOp]
            ReadMask [_StencilReadMask]
            WriteMask [_StencilWriteMask]
        }
        Cull Off
        Lighting Off
        ZWrite Off
        ZTest [unity_GUIZTestMode]
        Blend One OneMinusSrcAlpha
        ColorMask [_ColorMask]

        Pass
        {
            Name "Default"
        CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma target 2.0
            #include "UnityCG.cginc"
            #include "UnityUI.cginc"
            #pragma multi_compile_local _ UNITY_UI_CLIP_RECT
            #pragma multi_compile_local _ UNITY_UI_ALPHACLIP

            struct appdata_t
            {
                float4 vertex : POSITION;
                float4 color : COLOR;
                float2 texcoord : TEXCOORD0;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct v2f
            {
                float4 vertex : SV_POSITION;
                fixed4 color : COLOR;
                float2 uv : TEXCOORD0;
                float4 canvasPos : TEXCOORD1;
                UNITY_VERTEX_OUTPUT_STEREO
            };

            sampler2D _MainTex;
            float4 _MainTex_ST;
            fixed4 _Color;
            fixed4 _TextureSampleAdd;
            float4 _ClipRect;
            float _Mode, _Fill, _Ghost, _WaveAmp, _WaveFreq, _WaveSpeed, _Shine, _Heat, _Rage, _Pulse, _Deny, _T;

            v2f vert(appdata_t v)
            {
                v2f o;
                UNITY_SETUP_INSTANCE_ID(v);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.canvasPos = v.vertex;
                o.vertex = UnityObjectToClipPos(v.vertex);
                o.uv = TRANSFORM_TEX(v.texcoord, _MainTex);
                o.color = v.color * _Color;
                return o;
            }

            float hash(float2 p) { return frac(sin(dot(p, float2(127.1, 311.7))) * 43758.5453); }
            float noise(float2 p)
            {
                float2 i = floor(p), f = frac(p);
                float2 u = f * f * (3 - 2 * f);
                return lerp(lerp(hash(i), hash(i + float2(1, 0)), u.x), lerp(hash(i + float2(0, 1)), hash(i + float2(1, 1)), u.x), u.y);
            }

            fixed4 frag(v2f i) : SV_Target
            {
                // ---- nado: la ola viaja de la cabeza a la cola, más amplia hacia la cabeza
                float phase = i.canvasPos.x * _WaveFreq - _T * _WaveSpeed;
                float amp = _WaveAmp * lerp(0.55, 1.35, saturate(i.uv.x)) * (1 + _Rage * 0.4);
                float2 uv = i.uv;
                uv.y += sin(phase) * amp + sin(phase * 2.3 + 1.7) * amp * 0.18;

                fixed4 tex = tex2D(_MainTex, uv) + _TextureSampleAdd;
                float x = saturate(i.uv.x);
                half3 col = tex.rgb * i.color.rgb;
                half alpha = tex.a * i.color.a;
                half3 add = 0;

                // aura de fuego del Filo de Ira (solo el marco, que va detrás): alfa del cuerpo corrido
                // hacia abajo = halo que sube
                float aura = 0;
                if (_Rage > 0.001 && _Mode < 0.5)
                {
                    float wob = sin(uv.x * 38 + _T * 9) * 0.012;
                    aura += tex2D(_MainTex, uv + float2(wob, -0.06)).a * 0.55;
                    aura += tex2D(_MainTex, uv + float2(-wob, -0.12)).a * 0.32;
                    aura += tex2D(_MainTex, uv + float2(wob * 1.5, -0.19)).a * 0.18;
                    float fl = noise(float2(uv.x * 26, uv.y * 7 - _T * 5.5)) * noise(float2(uv.x * 9 + 3, uv.y * 3 - _T * 3.1));
                    aura *= (1 - tex.a) * saturate(fl * 2.4) * _Rage;
                }

                if (_Mode < 0.5)
                {
                    // marco: silueta oscura. En ira se calienta (rojo brasa); el pulso y el "no alcanza" lo marcan
                    col = lerp(col, col * half3(1.6, 0.45, 0.3) + half3(0.12, 0.01, 0), saturate(_Rage * 0.9 + _Heat * 0.25));
                    col += half3(0.55, 0.42, 0.1) * _Pulse * 0.5;
                    col = lerp(col, half3(0.85, 0.08, 0.05), _Deny * 0.6);
                }
                else
                {
                    // relleno: oro líquido con borde vivo
                    float edge = _Fill + 0.007 * sin(uv.y * 58 + _T * 6.5) + 0.004 * sin(uv.y * 23 - _T * 3.7);
                    float inside = step(x, edge) * step(0.0005, _Fill);
                    float ghost = step(edge, x) * step(x, max(_Ghost, edge));
                    float rim = inside * (1 - smoothstep(0.0, 0.035, edge - x));

                    // volumen: lomo más claro, panza más oscura
                    col *= lerp(0.74, 1.16, saturate((uv.y - 0.25) * 1.6));
                    // escamas: hileras grandes en arco (a este tamaño, un patrón fino hacía moiré)
                    float sc = sin(uv.x * 70 + sin(uv.y * 18) * 1.6) * 0.5 + 0.5;
                    col *= 0.95 + 0.07 * sc * sc;
                    // reflejo que recorre el cuerpo de la cola a la cabeza
                    float p = frac(_T * 0.16) * 1.5 - 0.25;
                    float shine = exp(-pow((x - p) / 0.05, 2)) * _Shine;
                    add += half3(1, 0.93, 0.68) * (shine * 0.5 + rim * 0.75) + _Pulse * half3(0.45, 0.38, 0.18);

                    // calor acumulado: entra rojo desde la cabeza
                    float heat = smoothstep(1.0 - _Heat * 1.02, 1.12 - _Heat, x) * _Heat;
                    col = lerp(col, col * half3(1.25, 0.5, 0.32) + half3(0.2, 0.02, 0), heat * 0.75);
                    // Filo de Ira: brasa viva que parpadea
                    float fl = 0.72 + 0.28 * noise(float2(uv.x * 18 - _T * 4, uv.y * 6 + _T * 2));
                    col = lerp(col, half3(1.0, 0.36, 0.12) * fl * 1.3, _Rage * 0.82);

                    col = lerp(col, half3(1, 0.95, 0.86), ghost);
                    col = lerp(col, col * half3(1.2, 0.35, 0.3), _Deny * 0.7);
                    alpha *= inside + ghost * 0.6;
                }

                // compuesto premultiplicado + aura aditiva (fuego)
                half3 fire = lerp(half3(1.0, 0.28, 0.06), half3(1.0, 0.82, 0.3), saturate(aura * 1.6)) * aura;
                half4 o;
                o.rgb = (col + add) * alpha + fire * 1.35;
                o.a = saturate(alpha + aura * 0.75);

                #ifdef UNITY_UI_CLIP_RECT
                half m = UnityGet2DClipping(i.canvasPos.xy, _ClipRect);
                o *= m;
                #endif
                #ifdef UNITY_UI_ALPHACLIP
                clip(o.a - 0.001);
                #endif
                return o;
            }
        ENDCG
        }
    }
}
