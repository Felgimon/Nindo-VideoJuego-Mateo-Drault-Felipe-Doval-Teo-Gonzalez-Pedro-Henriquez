// HUD de Nindō: la vida es la bandana roja del abuelo, y tiene que parecer tela.
//  * flamea: una ola suave recorre la banda y las puntas del nudo (izquierda del marco) se agitan más;
//    los pliegues toman la luz con la misma ola;
//  * relleno con borde vivo (antialias) y estela clara del daño que se vacía despacio (lo que se perdió);
//  * golpe: destello blanco corto (_Flash) y las puntas latiguean (_Hit); curarse: un brillo dorado
//    recorre la banda de izquierda a derecha (_Heal); poca vida: latido rojo (UIBeat, en _Low).
// El marco es 9-slice (el nudo no se estira): su uv.x no es lineal en pantalla, por eso la ola usa la
// posición en el canvas. Las puntas del nudo quedan en uv.x < _TailEnd (el borde izquierdo del slice).
// _Mode: 0 = marco (con el nudo), 1 = relleno. _T = tiempo sin escala. Basado en UI/Default.
Shader "Nindo/UI Bandana"
{
    Properties
    {
        [PerRendererData] _MainTex ("Sprite", 2D) = "white" {}
        _Color ("Tinte", Color) = (1, 1, 1, 1)
        _Mode ("0 marco / 1 relleno", Float) = 1
        _Fill ("Vida", Range(0, 1)) = 1
        _Ghost ("Estela de daño", Range(0, 1)) = 0
        _WaveAmp ("Flameo (uv)", Float) = 0.019
        _WaveFreq ("Frecuencia (por unidad de canvas)", Float) = 0.016
        _WaveSpeed ("Velocidad", Float) = 2.4
        _TailEnd ("Fin de las puntas del nudo (uv x del marco)", Float) = 0.17
        _Hit ("Golpe (latigazo de las puntas)", Range(0, 1)) = 0
        _Flash ("Destello del golpe", Range(0, 1)) = 0
        _Heal ("Curación: dónde va el brillo", Range(0, 1.5)) = 0
        _HealA ("Curación: intensidad", Range(0, 1)) = 0
        _Low ("Latido de poca vida", Range(0, 1)) = 0
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
            #pragma target 3.0
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
            float _Mode, _Fill, _Ghost, _WaveAmp, _WaveFreq, _WaveSpeed, _TailEnd, _Hit, _Flash, _Heal, _HealA, _Low, _T;

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

            fixed4 frag(v2f i) : SV_Target
            {
                float phase = i.canvasPos.x * _WaveFreq - _T * _WaveSpeed;
                // puntas del nudo: solo en el marco, más amplitud y aleteo propio
                float tails = _Mode < 0.5 ? 1 - smoothstep(_TailEnd * 0.45, _TailEnd, i.uv.x) : 0;
                float2 uv = i.uv;
                float whip = 1 + _Hit * 1.6;
                uv.y += sin(phase) * _WaveAmp * (0.35 + tails * 2.6) + sin(_T * 7.3 + i.uv.x * 40) * 0.006 * tails * whip;
                uv.x += sin(_T * 8.1 + i.uv.y * 13) * 0.005 * tails * whip;

                fixed4 tex = tex2D(_MainTex, uv) + _TextureSampleAdd;
                float aa = fwidth(i.uv.x) * 1.5;
                half3 col = tex.rgb * i.color.rgb;
                half alpha = tex.a * i.color.a;
                // pliegues: la luz sigue a la ola
                col *= 0.9 + 0.14 * cos(phase + 0.6);

                if (_Mode < 0.5)
                {
                    col = lerp(col, col + half3(0.45, 0.02, 0.02), _Low * 0.55);
                    col = lerp(col, half3(1, 1, 1), _Flash * 0.35);
                }
                else
                {
                    float x = saturate(i.uv.x);
                    float edge = _Fill + 0.006 * sin(uv.y * 40 + _T * 5);
                    float inside = smoothstep(-aa, aa, edge - x) * step(0.0005, _Fill);
                    float ghost = smoothstep(-aa, aa, x - edge) * smoothstep(-aa, aa, _Ghost - x);
                    float rim = inside * (1 - smoothstep(0, 0.03, edge - x));
                    // la banda ocupa la franja media del sprite (el margen es para el aleteo)
                    col *= lerp(0.78, 1.12, saturate((uv.y - 0.44) * 2.6));
                    col += rim * half3(0.9, 0.35, 0.3) + _Low * half3(0.35, 0.02, 0.02);
                    float hd = (x - _Heal) / 0.05;   // cuadrado a mano: pow() con base negativa es indefinido
                    col += half3(1, 0.85, 0.45) * exp(-hd * hd) * _HealA * 0.9;
                    col = lerp(col, half3(1, 0.88, 0.78), ghost * 0.85);
                    col = lerp(col, half3(1, 1, 1), _Flash * 0.85);
                    alpha *= saturate(inside + ghost * 0.75);
                }

                half4 o;
                o.rgb = col * alpha;
                o.a = alpha;
                #ifdef UNITY_UI_CLIP_RECT
                o *= UnityGet2DClipping(i.canvasPos.xy, _ClipRect);
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
