// Aviso de ataque en el suelo (legibilidad del parry desde la cámara alta).
// Un quad horizontal centrado en el atacante (v = hacia adelante). Dibuja:
//  * el anillo objetivo alrededor de los pies y un anillo que se acerca y lo alcanza EXACTO en el
//    impacto (_Progress = 1 - StrikeEta / eta inicial): se aprende el ritmo sin leer la animación;
//  * la zona que golpea: cuña (arco del golpe), disco (pisotón, centro corrido hacia adelante) o
//    carril (embestida / tajo a distancia), que se intensifica a medida que se acerca el golpe;
//  * _Window = dentro de la ventana del parry: destello blanco ("¡ahora!").
// Dorado = se puede desviar; rojo y dentado = imparable (dash). Sin texto ni kanji.
Shader "Nindo/Telegraph"
{
    Properties
    {
        _Color ("Color", Color) = (1, 0.82, 0.35, 1)
        _Progress ("Progreso hasta el golpe", Range(0, 1)) = 0
        _Window ("En la ventana del parry", Range(0, 1)) = 0
        _Danger ("Imparable", Range(0, 1)) = 0
        _Alpha ("Opacidad", Range(0, 1)) = 1
        _RingR ("Radio del anillo (0..1 del quad)", Float) = 0.25
        _Shape ("0 cuña, 1 disco, 2 carril", Float) = 0
        _ArcHalf ("Medio arco (rad)", Float) = 1.2
        _Range ("Alcance (0..1 del quad)", Float) = 0.8
        _Offset ("Centro del disco hacia adelante (0..1)", Float) = 0
        _Width ("Medio ancho del carril (0..1)", Float) = 0.12
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
                half4 _Color;
                float _Progress, _Window, _Danger, _Alpha, _RingR, _Shape, _ArcHalf, _Range, _Offset, _Width;
            CBUFFER_END

            struct A { float4 pos : POSITION; float2 uv : TEXCOORD0; UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct V { float4 pos : SV_POSITION; float2 p : TEXCOORD0; UNITY_VERTEX_OUTPUT_STEREO };

            V vert(A i)
            {
                V o;
                UNITY_SETUP_INSTANCE_ID(i);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.pos = TransformObjectToHClip(i.pos.xyz);
                o.p = i.uv * 2 - 1;   // -1..1, y = adelante
                return o;
            }

            float ring(float d, float r, float w) { return 1 - smoothstep(w * 0.5, w, abs(d - r)); }

            half4 frag(V i) : SV_Target
            {
                float2 p = i.p;
                float d = length(p);
                float ang = atan2(p.x, p.y);
                float t = _Time.y;
                float prog = saturate(_Progress);
                float ease = prog * prog;

                // ---- zona que golpea
                float zone = 0, zedge = 0;
                if (_Shape < 0.5)
                {
                    float r = _Range;
                    // borde dentado si es imparable
                    r *= 1 - _Danger * 0.06 * (0.5 + 0.5 * sin(ang * 22));
                    float inA = step(abs(ang), _ArcHalf);
                    zone = inA * step(d, r) * step(_RingR * 0.6, d);
                    zedge = inA * ring(d, r, 0.04) + step(d, r) * step(_RingR * 0.6, d) * (1 - smoothstep(0, 0.035, abs(abs(ang) - _ArcHalf) * d));
                }
                else if (_Shape < 1.5)
                {
                    float2 c = float2(0, _Offset);
                    float dd = length(p - c);
                    float r = _Range * (1 - _Danger * 0.05 * (0.5 + 0.5 * sin(atan2(p.x, p.y - _Offset) * 20)));
                    zone = step(dd, r);
                    zedge = ring(dd, r, 0.04);
                }
                else
                {
                    float inL = step(abs(p.x), _Width) * step(0, p.y) * step(p.y, _Range);
                    zone = inL;
                    zedge = step(0, p.y) * step(p.y, _Range) * (1 - smoothstep(0, 0.025, abs(abs(p.x) - _Width))) + step(abs(p.x), _Width) * ring(p.y, _Range, 0.04);
                }

                // ---- anillos de tiempo
                float target = ring(d, _RingR, 0.045);
                float approach = ring(d, lerp(_RingR * 2.6, _RingR, prog), 0.05 + 0.03 * (1 - prog));
                float core = (1 - smoothstep(0, _RingR, d)) * _Window * (0.6 + 0.4 * sin(t * 40));

                half3 col = _Color.rgb;
                half3 hot = lerp(half3(1, 0.97, 0.85), half3(1, 0.6, 0.5), _Danger);
                col = lerp(col, hot, _Window * 0.8);

                // líneas marcadas (fuerte) + relleno suave que crece hacia el golpe
                float lines = saturate(target * 0.85 + approach * (0.55 + 0.45 * prog) + zedge * (0.35 + 0.55 * ease) + _Window * target * 0.6);
                float fill = zone * (0.08 + 0.32 * ease) * (1 + _Window * 0.6);
                // franjas que corren hacia afuera en la zona (dirección del golpe)
                fill *= 0.75 + 0.25 * sin(d * 34 - t * 12);
                float a = saturate(lines + fill + core) * _Alpha;
                return half4(col * a * (1 + _Window * 0.8), a * 0.9);
            }
            ENDHLSL
        }
    }
}
