// Fuego facetado de los braseros del patio (FX/Braziers). La malla son lenguas de llama de 4-5 caras como las de
// los props (props_misc.fire_cluster) armadas por código; acá se mueven solas, sin costo de CPU:
//  color del vértice: r = altura en la lengua (0 base, 1 punta: cuánto se mece y titila), g = capa (0 afuera
//  rojo, 0.5 medio, 1 núcleo claro), b = fase de cada lengua, a = 0 para la cama de brasas (no crece ni se mece).
// _Size 0..1 enciende/apaga (las lenguas nacen de la brasa), _Bed es el brillo de las brasas que quedan al
// apagarse. Colores HDR por brasero (MaterialPropertyBlock): naranja en el Acto 1, violeta en el 2.
// Sin luz: emisivo puro con bloom; el sombreado facetado sale de las derivadas (cada cara un tono).
Shader "Nindo/Fire"
{
    Properties
    {
        [HDR] _Color ("Exterior", Color) = (2.4, 0.55, 0.12, 1)
        [HDR] _Mid ("Medio", Color) = (3.2, 1.25, 0.25, 1)
        [HDR] _Core ("Núcleo", Color) = (4.0, 2.9, 1.1, 1)
        _Size ("Tamaño (0 apagado)", Range(0, 1.5)) = 1
        _Bed ("Brasas", Range(0, 1)) = 1
        _Sway ("Vaivén (m)", Float) = 0.07
        _Speed ("Velocidad", Float) = 1
        _Seed ("Semilla", Float) = 0
    }

    SubShader
    {
        Tags { "RenderType" = "Opaque" "Queue" = "Geometry+10" "RenderPipeline" = "UniversalPipeline" "IgnoreProjector" = "True" }
        Cull Off

        Pass
        {
            Name "Fire"
            Tags { "LightMode" = "UniversalForward" }
            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_fog
            #pragma multi_compile_instancing
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

            CBUFFER_START(UnityPerMaterial)
                half4 _Color, _Mid, _Core;
                float _Size, _Bed, _Sway, _Speed, _Seed;
            CBUFFER_END

            struct A { float4 pos : POSITION; half4 color : COLOR; UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct V { float4 pos : SV_POSITION; float3 wpos : TEXCOORD0; half4 c : TEXCOORD1; float fog : TEXCOORD2; UNITY_VERTEX_OUTPUT_STEREO };

            V vert(A i)
            {
                V o;
                UNITY_SETUP_INSTANCE_ID(i);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                float3 p = i.pos.xyz;
                float h = i.color.r;
                float tongue = i.color.a;                 // 0 = cama de brasas
                float ph = i.color.b * 6.2832 + _Seed;
                float t = _Time.y * _Speed;
                // titileo: cada lengua se estira y encoge a su ritmo, más en la punta
                float fl = 1.0 + (0.16 * sin(t * 9.1 + ph * 3.0) + 0.09 * sin(t * 14.3 + ph)) * h;
                // apagada (_Size 0) cada lengua se encoge a un punto debajo de las brasas: no queda una tapa plana encima
                float grow = saturate(_Size);
                p.y = lerp(p.y, p.y * fl * _Size - (1.0 - grow) * 0.06, tongue);
                p.xz *= lerp(1.0, grow, tongue);
                // vaivén: las puntas se mecen y se tuercen un poco
                float2 sway = float2(sin(t * 2.3 + ph), cos(t * 1.9 + ph * 1.7)) * _Sway * h * h * tongue * _Size;
                p.xz += sway;
                float tw = sin(t * 3.1 + ph) * 0.35 * h * tongue;
                float c = cos(tw), s = sin(tw);
                p.xz = float2(p.x * c - p.z * s, p.x * s + p.z * c);
                o.wpos = TransformObjectToWorld(p);
                o.pos = TransformWorldToHClip(o.wpos);
                o.c = i.color;
                o.fog = ComputeFogFactor(o.pos.z);
                return o;
            }

            half4 frag(V i) : SV_Target
            {
                float layer = i.c.g, h = i.c.r, tongue = i.c.a;
                half3 col = layer < 0.5 ? lerp(_Color.rgb, _Mid.rgb, layer * 2.0) : lerp(_Mid.rgb, _Core.rgb, layer * 2.0 - 1.0);
                // las puntas de afuera se oscurecen hacia el rojo; el núcleo sigue claro
                col *= lerp(1.0, 0.62, h * h * (1.0 - layer));
                // facetas: cada cara con su tono según hacia dónde mira (como las llamas de los props)
                float3 n = normalize(cross(ddy(i.wpos), ddx(i.wpos)));
                float3 v = normalize(GetCameraPositionWS() - i.wpos);
                col *= 0.78 + 0.32 * abs(dot(n, v));
                // cama de brasas: brilla según _Bed (lo que queda al apagarse) y late despacio
                float bed = (0.75 + 0.25 * sin(_Time.y * 2.1 + i.wpos.x * 7.0 + i.wpos.z * 5.0)) * _Bed;
                col = lerp(_Core.rgb * 0.55 * bed, col, tongue);
                return half4(MixFog(col, i.fog), 1);
            }
            ENDHLSL
        }
    }
    Fallback Off
}
