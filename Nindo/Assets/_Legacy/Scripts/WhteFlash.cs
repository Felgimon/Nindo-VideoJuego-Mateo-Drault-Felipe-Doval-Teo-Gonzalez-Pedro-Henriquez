using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class WhteFlash : MonoBehaviour
{
    [Header("Renderer con los materiales del enemigo")]
    public SkinnedMeshRenderer skinned;

    [Header("Duración del efecto al recibir daño")]
    public float flashDuration = 0.15f;

    private Material[] mats;

    private void Start()
    {
        // Instancia local de todos los materiales
        mats = skinned.materials;
    }

    public void Flash()
    {
        // Por si recibe varios golpes seguidos
        StopAllCoroutines();
        StartCoroutine(FlashRoutine());
    }

    private void Update()
    {
        if (Input.GetKeyUp(KeyCode.Z))
        {
        }
    }
    private IEnumerator FlashRoutine()
    {
        float flashAmount = 1f;

        while (flashAmount > 0f)
        {
            flashAmount -= Time.deltaTime / flashDuration;

            // Aplicar el valor a TODOS los materiales
            for (int i = 0; i < mats.Length; i++)
            {
                mats[i].SetFloat("_Amount", flashAmount);
            }

            yield return null;
        }
    }
}
