// Sombra viva de Kokuyō (FX/PlanarShadow). Se dibuja con la malla de un "doble" del jefe (mismos huesos):
// cada vértice se proyecta al piso según la luz de la luna (_LightDir), así la silueta se estira ~6 m hacia la
// cámara y actúa el golpe ANTES que el cuerpo (el doble puede ir adelantado). No es una sombra real: es tinta.
//  - Pasada "InkBleed": la misma silueta inflada hacia afuera (normal proyectada al piso) con ruido: un borde
//    corrido de tinta que respira y se estira en la dirección de la sombra. Escribe el bit 64 del stencil.
//  - Pasada "InkCore": el cuerpo de tinta violeta (#24163a, 0.72) con vetas que corren de los pies a la punta.
//    Escribe el bit 128: cada píxel se tiñe una sola vez aunque se pisen brazos, piernas y espada.
// _Rise 0 -> 1: la sombra se despega del piso (la punta primero) y se para como una figura de humo de tinta con
// borde violeta (Kage, la sombra arrancada); el borde corrido pasa a ser el humo que la envuelve.
// Recortes: fuera de la arena (_ArenaCenter.w) y un hueco alrededor de Kaito (_Hole: el lazo de la bandana la
// empuja: Kaito nunca queda parado sobre negro). Va antes que los avisos ensō (Transparent-20): nunca los tapa.
Shader "Nindo/ShadowInk"
{
    Properties
    {
        _Color ("Tinta", Color) = (0.141, 0.086, 0.227, 1)
        _Alpha ("Opacidad del cuerpo", Range(0, 1)) = 0.72
        _BleedAlpha ("Opacidad del borde corrido", Range(0, 1)) = 0.36
        _Bleed ("Ancho del borde corrido (m)", Float) = 0.24
        _Boil ("Hervor de la tinta (m)", Float) = 0.07
        _LightDir ("Hacia donde viaja la luz", Vector) = (0, -0.574, -0.819, 0)
        _Stretch ("Estiramiento", Float) = 1
        _GroundY ("Altura del piso", Float) = 0
        _Lift ("Separación del piso (m)", Float) = 0.04
        _Origin ("Pies del cuerpo (xyz) y alto (w)", Vector) = (0, 0, 0, 4.5)
        _ArenaCenter ("Centro de la arena (xyz) y radio (w)", Vector) = (0, 0, 0, 19)
        _Hole ("Hueco del lazo: posición (xyz), radio (w)", Vector) = (0, 0, 0, 0)
        _HoleSoft ("Borde del hueco (m)", Float) = 0.4
        _Pulse ("Pulso del golpe", Range(0, 1)) = 0
        _PulseColor ("Color del pulso", Color) = (0.227, 0.078, 0.376, 1)
        _Rise ("Levantada (0 piso, 1 figura)", Range(0, 1)) = 0
        _RimColor ("Borde de la figura", Color) = (0.753, 0.541, 1, 1)
        _Fade ("Visibilidad", Range(0, 1)) = 1
    }

    SubShader
    {
        Tags { "RenderType" = "Transparent" "Queue" = "Transparent-20" "RenderPipeline" = "UniversalPipeline" "IgnoreProjector" = "True" }
        Blend SrcAlpha OneMinusSrcAlpha
        ZWrite Off
        ZTest LEqual
        Cull Off
        Offset -1, -1

        HLSLINCLUDE
        #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

        CBUFFER_START(UnityPerMaterial)
            half4 _Color, _PulseColor, _RimColor;
            float4 _LightDir, _Origin, _ArenaCenter, _Hole;
            float _Alpha, _BleedAlpha, _Bleed, _Boil, _Stretch, _GroundY, _Lift, _HoleSoft, _Pulse, _Rise, _Fade;
        CBUFFER_END

        struct A { float4 pos : POSITION; float3 normal : NORMAL; UNITY_VERTEX_INPUT_INSTANCE_ID };
        struct V
        {
            float4 pos : SV_POSITION;
            float3 wpos : TEXCOORD0;
            float3 nrm : TEXCOORD1;
            float4 info : TEXCOORD2;     // x: altura normalizada en el cuerpo, y: levantada del vértice, z: niebla
            UNITY_VERTEX_OUTPUT_STEREO
        };

        float hash31(float3 p)
        {
            p = frac(p * 0.1031);
            p += dot(p, p.zyx + 31.32);
            return frac((p.x + p.y) * p.z);
        }

        float vnoise(float3 p)
        {
            float3 i = floor(p), f = frac(p);
            float3 u = f * f * (3.0 - 2.0 * f);
            float a = lerp(lerp(hash31(i), hash31(i + float3(1, 0, 0)), u.x), lerp(hash31(i + float3(0, 1, 0)), hash31(i + float3(1, 1, 0)), u.x), u.y);
            float b = lerp(lerp(hash31(i + float3(0, 0, 1)), hash31(i + float3(1, 0, 1)), u.x), lerp(hash31(i + float3(0, 1, 1)), hash31(i + float3(1, 1, 1)), u.x), u.y);
            return lerp(a, b, u.z);
        }

        float3 LightDir()
        {
            float3 L = normalize(_LightDir.xyz);
            L.y = min(L.y, -0.08);          // nunca rasante: la sombra no se va al infinito
            return normalize(L);
        }

        // Proyecta un punto del cuerpo al piso y lo mezcla con su lugar real según la levantada.
        // bleed > 0: además lo empuja hacia afuera de la silueta (borde corrido / humo).
        V Ink(A i, float bleed)
        {
            V o;
            UNITY_SETUP_INSTANCE_ID(i);
            UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
            float3 P = TransformObjectToWorld(i.pos.xyz);
            float3 N = normalize(TransformObjectToWorldNormal(i.normal));
            float3 L = LightDir();
            float t = _Time.y;

            float h = max(P.y - _GroundY, 0.0);
            float hn = saturate(h / max(_Origin.w, 0.1));
            float2 flat = L.xz / -L.y;
            float3 G = float3(P.x + flat.x * h * _Stretch, _GroundY + _Lift, P.z + flat.y * h * _Stretch);

            // hervor: la tinta se mueve sola, más lejos de los pies (la sombra está viva y no del todo quieta)
            float2 q = G.xz * 0.55;
            float2 boil = float2(vnoise(float3(q, t * 0.7)), vnoise(float3(q + 17.3, t * 0.7 + 3.1))) - 0.5;
            G.xz += boil * _Boil * (0.35 + 1.6 * hn);

            // borde corrido: la normal proyectada al piso a lo largo de la luz apunta hacia afuera de la silueta
            // (y es ~0 en las caras que miran a la luz o le dan la espalda: el interior no se mueve)
            float3 Np = N - L * (N.y / L.y);
            float sl = length(Np.xz);
            float2 outDir = sl > 1e-4 ? Np.xz / sl : float2(0, 0);
            float wob = 0.35 + 0.9 * vnoise(float3(G.xz * 1.3, t * 0.35));
            G.xz += outDir * bleed * wob * saturate(sl);

            // levantada: la punta (lo más alto del cuerpo) se despega primero y la figura se para sobre los pies
            float rv = saturate(_Rise * 2.0 - (1.0 - hn));
            float3 smoke = float3(boil.x, abs(boil.y) * 0.8, boil.y) * _Boil * 1.8 * hn;
            float3 R = P + smoke + N * bleed * 0.55 * wob;
            float3 W = lerp(G, R, rv);

            o.wpos = W;
            o.nrm = N;
            o.pos = TransformWorldToHClip(W);
            o.info = float4(hn, rv, ComputeFogFactor(o.pos.z), 0);
            return o;
        }

        // recortes de la sombra en el piso: borde de la arena y el hueco alrededor de Kaito
        float GroundMask(float3 w, float rv)
        {
            float dA = distance(w.xz, _ArenaCenter.xz);
            float arena = 1.0 - smoothstep(_ArenaCenter.w - 1.5, _ArenaCenter.w, dA);
            float hole = _Hole.w > 0.01 ? smoothstep(_Hole.w, _Hole.w + _HoleSoft, distance(w.xz, _Hole.xz)) : 1.0;
            return lerp(arena * hole, 1.0, rv) * _Fade;
        }

        // coordenadas a lo largo (v) y a lo ancho (u) de la sombra: las vetas corren de los pies a la punta
        float2 InkUV(float3 w)
        {
            float3 L = LightDir();
            float2 D = normalize(L.xz + float2(1e-5, 0));
            float2 rel = w.xz - _Origin.xz;
            return float2(dot(rel, float2(-D.y, D.x)), dot(rel, D));
        }
        ENDHLSL

        Pass
        {
            Name "InkBleed"
            Tags { "LightMode" = "SRPDefaultUnlit" }
            Stencil { Ref 64 ReadMask 192 WriteMask 192 Comp Greater Pass Replace }
            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_fog
            #pragma multi_compile_instancing

            V vert(A i) { return Ink(i, _Bleed); }

            half4 frag(V i) : SV_Target
            {
                float t = _Time.y;
                float rv = i.info.y;
                float2 uv = InkUV(i.wpos);
                // en el piso: tinta que se corre en hilos a lo largo de la sombra; parada: humo que sube
                float nGround = vnoise(float3(uv.x * 2.6, uv.y * 0.7 - t * 0.45, t * 0.15)) * 0.65
                              + vnoise(float3(uv.x * 6.0, uv.y * 1.8 - t * 0.9, 7.0)) * 0.35;
                float nSmoke = vnoise(float3(i.wpos.x * 2.2, i.wpos.y * 1.6 - t * 1.3, i.wpos.z * 2.2));
                float n = lerp(nGround, nSmoke, rv);
                float a = smoothstep(0.38, 0.58, n) * _BleedAlpha;
                a *= GroundMask(i.wpos, rv);
                half3 col = lerp(_Color.rgb, _RimColor.rgb * 0.5, rv * 0.35);
                col = lerp(col, _PulseColor.rgb * 2.2, _Pulse * 0.6);
                col = MixFog(col, i.info.z);
                return half4(col, saturate(a));
            }
            ENDHLSL
        }

        Pass
        {
            Name "InkCore"
            Tags { "LightMode" = "UniversalForward" }
            Stencil { Ref 128 ReadMask 192 WriteMask 192 Comp Greater Pass Replace }
            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_fog
            #pragma multi_compile_instancing

            V vert(A i) { return Ink(i, 0.0); }

            half4 frag(V i, FRONT_FACE_TYPE face : FRONT_FACE_SEMANTIC) : SV_Target
            {
                float t = _Time.y;
                float rv = i.info.y;
                float2 uv = InkUV(i.wpos);
                // vetas: la tinta corre de los pies hacia la punta, más seca (rayada) cerca de la punta
                float streak = vnoise(float3(uv.x * 3.2, uv.y * 0.55 - t * 0.35, 1.7));
                float dry = smoothstep(0.55, 1.0, i.info.x) * smoothstep(0.62, 0.8, vnoise(float3(uv.x * 9.0, uv.y * 0.9, 4.2)));
                float a = _Alpha * (0.86 + 0.24 * streak) * (1.0 - 0.45 * dry);
                half3 col = _Color.rgb * (0.85 + 0.3 * streak);

                // parada: figura de humo de tinta, oscura por dentro, borde violeta y la parte de arriba que se deshace
                float3 viewDir = normalize(GetCameraPositionWS() - i.wpos);
                float3 N = normalize(i.nrm) * IS_FRONT_VFACE(face, 1.0, -1.0);
                // borde fino (potencia alta): desde la cámara alta casi todas las caras están de costado y con un borde
                // ancho la figura se leía como un fantasma lila; tiene que ser tinta negra-violeta con un filo de luz
                float rim = pow(1.0 - saturate(abs(dot(N, viewDir))), 3.5);
                float smoke = vnoise(float3(i.wpos.x * 2.4, i.wpos.y * 1.8 - t * 1.4, i.wpos.z * 2.4));
                float keep = smoothstep(0.12, 0.42, smoke + (1.0 - i.info.x) * 0.75);
                half3 figure = lerp(_Color.rgb * (0.38 + 0.15 * streak), _RimColor.rgb * 1.5, rim);
                col = lerp(col, figure, rv);
                a = lerp(a, (0.88 + 0.12 * rim) * keep, rv);

                // golpe de la sombra: un instante más saturada y brillante (lee como el "¡ahora!" en el piso)
                col = lerp(col, _PulseColor.rgb * 2.6, _Pulse);
                a = lerp(a, max(a, 0.9), _Pulse);
                a *= GroundMask(i.wpos, rv);
                col = MixFog(col, i.info.z);
                return half4(col, saturate(a));
            }
            ENDHLSL
        }
    }
    Fallback Off
}
