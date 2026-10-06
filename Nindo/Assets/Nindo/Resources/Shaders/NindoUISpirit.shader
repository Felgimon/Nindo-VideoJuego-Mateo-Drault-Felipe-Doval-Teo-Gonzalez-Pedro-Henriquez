// HUD de Nindō: el dragón dorado del Espíritu de la Bandana, vivo.
//  * nada: la ola viaja de la cabeza a la cola (como una serpiente) y es más amplia en la cola; el cuello
//    se endurece y la cabeza casi no se mueve (el ojo, que pone la UI, no se despega de la cuenca). La
//    cabeza además cabecea (_Nod) y el cuerpo respira (escala, en C#);
//  * el relleno es oro líquido: borde vivo, volumen (lomo claro, panza oscura), escamas que destellan y
//    un reflejo que recorre el cuerpo de la cola a la cabeza; al gastar queda una estela pálida que se
//    deshace en motas; si no alcanza, se raya en rojo lo que falta (_Need); sin Espíritu para el dash el
//    oro se apaga (_Dim);
//  * Filo de Ira vive en el LOMO, aparte del Espíritu: la cresta se enciende como brasa desde la cola hasta
//    _RageFront (lo cargado). Lista para encenderse (_Ready) le asoman lenguas de fuego; activa (_RageOn)
//    el dragón arde y las llamas se achican hacia la cola con el tiempo que queda (el mismo _RageFront,
//    que PlayerController vacía con el temporizador). Así se lee aunque el Espíritu esté vacío.
// _Mode: 0 = marco (silueta oscura, va detrás y dibuja las llamas), 1 = relleno.
// u = posición a lo largo del dragón (0 cola, 1 hocico), igual en el marco y en el relleno: uv.x * _UScale +
// _UOffset. La ola usa u * _Len (ancho en unidades de canvas) y no la posición del vértice: no depende de
// dónde esté el HUD ni de los canvas anidados, y UIManager la repite en C# para el ojo y las brasas.
// El tiempo llega sin escala desde UIManager (_T). Basado en UI/Default (stencil, máscaras, clip rect).
Shader "Nindo/UI Spirit"
{
    Properties
    {
        [PerRendererData] _MainTex ("Sprite", 2D) = "white" {}
        _Dorsal ("Perfil del lomo (R cresta, G piel, B panza; v)", 2D) = "black" {}
        _Color ("Tinte", Color) = (1, 1, 1, 1)
        _Mode ("0 marco / 1 relleno", Float) = 1
        _UScale ("u por uv.x", Float) = 1
        _UOffset ("u en uv.x = 0", Float) = 0
        _Len ("Largo del dragón (unidades de canvas)", Float) = 560
        _Height ("Alto del quad (unidades de canvas)", Float) = 123
        _Fill ("Relleno", Range(0, 1)) = 1
        _Ghost ("Estela al gastar", Range(0, 1)) = 0
        _GhostAge ("Estela: cuánto se deshizo", Range(0, 1)) = 0
        _Need ("Hasta dónde haría falta", Range(0, 1)) = 0
        _NeedA ("Aviso de lo que falta", Range(0, 1)) = 0
        _WaveAmp ("Ondulación (uv)", Float) = 0.024
        _WaveFreq ("Frecuencia (por unidad de canvas)", Float) = 0.012
        _WaveSpeed ("Velocidad de la ondulación", Float) = 1.8
        _Nod ("Cabeceo (uv)", Float) = 0
        _Shine ("Brillo de escamas", Range(0, 1)) = 0.7
        _RageFront ("Ira: frente (carga o tiempo que queda)", Range(0, 1)) = 0
        _Ready ("Ira lista para encenderse", Range(0, 1)) = 0
        _RageOn ("Filo de Ira activo", Range(0, 1)) = 0
        _Pulse ("Pulso (ganó espíritu)", Range(0, 1)) = 0
        _Deny ("No alcanza el espíritu", Range(0, 1)) = 0
        _Dim ("Sin espíritu para el dash", Range(0, 1)) = 0
        _Spark ("Destello de umbral", Range(0, 1)) = 0
        _SparkX ("Dónde (x del relleno)", Range(0, 1)) = 0
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

            sampler2D _MainTex, _Dorsal;
            float4 _MainTex_ST;
            fixed4 _Color;
            fixed4 _TextureSampleAdd;
            float4 _ClipRect;
            float _Mode, _UScale, _UOffset, _Len, _Height, _Fill, _Ghost, _GhostAge, _Need, _NeedA;
            float _WaveAmp, _WaveFreq, _WaveSpeed, _Nod, _Shine, _RageFront, _Ready, _RageOn;
            float _Pulse, _Deny, _Dim, _Spark, _SparkX, _T;

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

            // pow() con base negativa es indefinido en la GPU: los cuadrados van multiplicados
            float sq(float x) { return x * x; }
            float hash(float2 p) { return frac(sin(dot(p, float2(127.1, 311.7))) * 43758.5453); }
            float noise(float2 p)
            {
                float2 i = floor(p), f = frac(p);
                float2 u = f * f * (3 - 2 * f);
                return lerp(lerp(hash(i), hash(i + float2(1, 0)), u.x), lerp(hash(i + float2(0, 1)), hash(i + float2(1, 1)), u.x), u.y);
            }

            // muestras extra sin derivadas (tex2Dlod): van dentro de ramas y los sprites de UI no tienen mips
            float Alpha(float2 p) { return tex2Dlod(_MainTex, float4(p, 0, 0)).a; }

            // amplitud de la ola a lo largo del cuerpo: cola suelta, cuello firme, cabeza casi quieta
            // (UIManager.DragonWave repite esta misma curva)
            float Envelope(float u)
            {
                float e = lerp(1.25, 1.15, saturate(u / 0.15));
                e = u > 0.15 ? lerp(1.15, 0.9, saturate((u - 0.15) / 0.6)) : e;
                e = u > 0.75 ? lerp(0.9, 0.35, saturate((u - 0.75) / 0.11)) : e;
                e = u > 0.86 ? lerp(0.35, 0.25, saturate((u - 0.86) / 0.14)) : e;
                return e;
            }

            fixed4 frag(v2f i) : SV_Target
            {
                float u = i.uv.x * _UScale + _UOffset;
                float aa = fwidth(i.uv.x) * 1.5;   // antialias de los bordes del relleno (fuera de las ramas)
                // ---- nado: fase u*Len*k + w*t -> las crestas viajan hacia la cola
                float amp = _WaveAmp * Envelope(saturate(u)) * (1 + _RageOn * 0.25);
                float ph = u * _Len * _WaveFreq + _T * _WaveSpeed;
                float2 uv = i.uv;
                uv.y += sin(ph) * amp + sin(ph * 2.3 + 1.7) * amp * 0.18 + _Nod * smoothstep(0.80, 0.98, u);

                fixed4 tex = tex2D(_MainTex, uv) + _TextureSampleAdd;
                half3 col = tex.rgb * i.color.rgb;
                half alpha = tex.a * i.color.a;
                half3 add = 0;
                float fire = 0;

                // ---- Filo de Ira en el lomo: borde de arriba de la silueta (cresta incluida) hasta el frente
                float above = Alpha(uv + float2(0, 0.045));
                float rim = tex.a * (1 - above);
                float gate = smoothstep(-0.02, 0.0, _RageFront - u) * step(0.002, _RageFront);
                // chispa en la punta de la carga, solo sobre el lomo (en toda la columna parecía una barra)
                float tip = exp(-sq((u - _RageFront) / 0.012)) * step(0.002, _RageFront) * (1 - _RageOn) * (1 - Alpha(uv + float2(0, 0.11)));
                float glow = _Ready > 0.5 ? 0.6 + 0.4 * sin(_T * 3.2) : 0.85;
                glow *= 0.82 + 0.18 * noise(float2(u * 40 - _T * 2.2, 3.1));
                half3 ember = _Mode < 0.5 ? half3(1.0, 0.42, 0.08) * 1.15 : half3(0.95, 0.16, 0.04) * 1.15;

                if (_Mode < 0.5)
                {
                    // ---- llamas: lenguas que suben desde la piel del lomo (perfil medido del sprite, sin las púas):
                    // cada una con su alto (ruido por columna que se mueve) y turbulencia adentro que sube.
                    // Antes se sacaban corriendo la silueta hacia arriba y se leían como copias rayadas del dragón
                    float inten = max(_Ready * 0.6, _RageOn);
                    if (inten > 0.001 && tex.a < 0.99)
                    {
                        float reach = lerp(0.085, 0.16, _RageOn);
                        float sway = sin(uv.y * 34 + _T * 5.3) * 0.004;
                        float hgt = (uv.y - tex2Dlod(_Dorsal, float4(saturate(u), 0.5, 0, 0)).g) / reach;
                        float lim = 0.3 + 0.85 * noise(float2((u + sway) * 15 + _T * 0.6, _T * 1.9));
                        float turb = noise(float2((u + sway) * 40, hgt * 3.2 - _T * 5.5)) * 0.65
                                   + noise(float2((u + sway) * 90 + 3, hgt * 6 - _T * 9)) * 0.35;
                        fire = saturate((1 - hgt / lim) * 1.5 + (turb - 0.55) * 1.6) * step(-0.2, hgt) * (1 - tex.a) * gate * inten;
                    }
                    // marco: silueta oscura. Activo, se calienta (más dentro del frente: se ve cuánto queda)
                    float hot = (0.8 * gate + 0.35 * (1 - gate)) * _RageOn;
                    col = lerp(col, col * half3(1.6, 0.45, 0.3) + half3(0.12, 0.01, 0), hot);
                    col = lerp(col, ember, saturate(rim * gate * glow + tip * tex.a * 0.9));
                    col += half3(0.55, 0.42, 0.1) * _Pulse * 0.5;
                    col = lerp(col, half3(0.85, 0.08, 0.05), _Deny * 0.6);
                }
                else
                {
                    float xf = saturate(i.uv.x);
                    // ---- oro líquido con borde vivo (antialias con fwidth: a 560 px el step() serruchaba)
                    float edge = _Fill + 0.007 * sin(uv.y * 58 + _T * 6.5) + 0.004 * sin(uv.y * 23 - _T * 3.7);
                    float inside = smoothstep(-aa, aa, edge - xf) * step(0.0005, _Fill);
                    float trail = smoothstep(-aa, aa, xf - edge) * smoothstep(-aa, aa, _Ghost - xf);
                    // la estela se deshace en motas mientras se vacía
                    float gn = noise(float2(xf * 300, uv.y * 90)) * 0.6 + noise(float2(xf * 60, uv.y * 18)) * 0.4;
                    trail *= saturate((gn * 0.6 + 0.55 - _GhostAge * 1.15) * 5);
                    float need = smoothstep(-aa, aa, xf - max(edge, _Ghost)) * smoothstep(-aa, aa, _Need - xf) * _NeedA;
                    float rimF = inside * (1 - smoothstep(0.0, 0.035, edge - xf));

                    // volumen: lomo claro y panza oscura, siguiendo la curva del cuerpo
                    float up = Alpha(uv + float2(0, 0.07));
                    float dn = Alpha(uv - float2(0, 0.07));
                    col *= 1 + 0.2 * (1 - up) - 0.24 * (1 - dn);
                    // escamas: hileras grandes en arco (un patrón fino hacía moiré) y destellos sueltos
                    float sc = sin(xf * 70 + sin(uv.y * 18) * 1.6) * 0.5 + 0.5;
                    col *= 0.95 + 0.07 * sc * sc;
                    float2 cp = float2(xf * 90, uv.y * 26);
                    float h = hash(floor(cp));
                    float2 cf = frac(cp) - 0.5;
                    float twinkle = pow(saturate(sin(_T * 2.3 + h * 50)), 16) * step(0.93, h) * saturate(1 - length(float2(cf.x, cf.y * 0.6)) * 3.2);
                    // reflejo que recorre el cuerpo de la cola a la cabeza cada ~6 s
                    float p = frac(_T * 0.16) * 1.5 - 0.25;
                    float shine = exp(-sq((xf - p) / 0.05)) * _Shine;
                    add += half3(1, 0.93, 0.68) * (shine * 0.5 + rimF * 0.75 + twinkle * 0.6) * (1 - _Dim * 0.7);
                    add += _Pulse * half3(0.45, 0.38, 0.18) + half3(1, 0.95, 0.75) * exp(-sq((xf - _SparkX) / 0.018)) * _Spark * 1.4;

                    // sin Espíritu para el dash: el oro se apaga (desatura) y deja de brillar
                    half lum = dot(col, half3(0.3, 0.59, 0.11));
                    col = lerp(col, lum * half3(0.9, 0.84, 0.72), 0.45 * _Dim);
                    // Filo de Ira: brasa viva, más fuerte detrás del frente (el tiempo que queda)
                    float fl = 0.72 + 0.28 * noise(float2(xf * 18 - _T * 4, uv.y * 6 + _T * 2));
                    col = lerp(col, half3(1.0, 0.36, 0.12) * fl * 1.3, _RageOn * (0.45 + 0.4 * gate));
                    col = lerp(col, ember, saturate(rim * gate * glow * 0.9));

                    col = lerp(col, half3(0.85, 0.78, 0.55), trail);
                    col = lerp(col, col * half3(1.2, 0.35, 0.3), _Deny * 0.7);
                    // lo que falta para pagar: rayado rojo sobre el cuerpo vacío, diagonal en unidades de canvas
                    // (en uv se estiraba con el sprite)
                    float stripe = step(0.5, frac((u * _Len + uv.y * _Height) / 9));
                    col = lerp(col, half3(0.95, 0.15, 0.1), need);
                    alpha *= saturate(inside + trail * 0.45 + need * (0.45 + 0.4 * stripe));
                }

                // compuesto premultiplicado + fuego aditivo: base roja, cuerpo naranja, puntas amarillas
                half3 fc = fire < 0.5 ? lerp(half3(0.8, 0.1, 0.03), half3(1.0, 0.45, 0.08), fire * 2) : lerp(half3(1.0, 0.45, 0.08), half3(1.0, 0.9, 0.5), fire * 2 - 1);
                half4 o;
                o.rgb = (col + add) * alpha + fc * fire * 1.35;
                o.a = saturate(alpha + fire * 0.8);

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
