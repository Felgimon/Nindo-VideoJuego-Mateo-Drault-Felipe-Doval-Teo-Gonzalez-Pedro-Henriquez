using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class EnemyBase : MonoBehaviour
{
    public virtual void InterruptAttack()
    {
        Debug.Log($"{gameObject.name} fue interrumpido (base)");
    }
}
